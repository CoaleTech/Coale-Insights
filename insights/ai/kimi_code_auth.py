# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Kimi Code subscription auth for the Moonshot provider.

Kimi has two entirely separate auth worlds and they are NOT interchangeable:

- Moonshot Open Platform — a metered API key against ``api.moonshot.ai``.
- Kimi Code subscription  — OAuth against ``auth.kimi.com``, served from
  ``api.kimi.com/coding/v1``. An Open Platform key is rejected here with 401.

This module implements the subscription side using the RFC 8628 device flow,
which needs no browser on the server:

    1. POST /api/oauth/device_authorization -> device_code + user_code
    2. operator approves at kimi.com/code/authorize_device
    3. POST /api/oauth/token                -> access + refresh token
       (returns 400 `authorization_pending` until step 2 completes)
"""

import time
import uuid
from typing import Any, Dict, Optional

import frappe
import requests
from frappe import _

CLIENT_ID = "17e5f671-d194-4dfb-9706-5516cb48c098"
DEFAULT_OAUTH_HOST = "https://auth.kimi.com"
CODING_BASE_URL = "https://api.kimi.com/coding/v1"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

PENDING_CACHE_KEY = "insights:kimi_code_device_login"
PENDING_TTL = 1800  # Kimi device codes live 30 minutes
REFRESH_SKEW = 120

# Models served by the Kimi Code subscription (distinct from Open Platform ids).
SUBSCRIPTION_MODELS = ["kimi-for-coding", "kimi-for-coding-highspeed"]


def _oauth_host() -> str:
	import os

	return (
		os.environ.get("KIMI_CODE_OAUTH_HOST")
		or os.environ.get("KIMI_OAUTH_HOST")
		or DEFAULT_OAUTH_HOST
	).rstrip("/")


def _guard():
	frappe.has_permission("Insights Settings", "write", throw=True)


def _device_id() -> str:
	"""Stable per-site device id; Kimi ties the grant to it."""
	settings = frappe.get_single("Insights Settings")
	existing = getattr(settings, "kimi_device_id", None)
	if existing:
		return existing
	generated = uuid.uuid4().hex
	frappe.db.set_single_value("Insights Settings", "kimi_device_id", generated)
	frappe.db.commit()
	return generated


def _headers() -> Dict[str, str]:
	"""Identify as a Kimi CLI-style client; the device id must be stable."""
	return {
		"Content-Type": "application/x-www-form-urlencoded",
		"User-Agent": "InsightsAI/1.0",
		"X-Msh-Platform": "kimi_cli",
		"X-Msh-Device-Id": _device_id(),
	}


def _persist(tokens: Dict[str, Any]):
	access = tokens.get("access_token") or ""
	if not access:
		frappe.throw(_("Kimi returned no access token."))
	expires_in = int(tokens.get("expires_in") or 3600)

	set_value = frappe.db.set_single_value
	set_value("Insights Settings", "kimi_oauth_access_token", access)
	if tokens.get("refresh_token"):
		set_value("Insights Settings", "kimi_oauth_refresh_token", tokens["refresh_token"])
	set_value("Insights Settings", "kimi_oauth_expires_at", int(time.time()) + expires_in)
	set_value("Insights Settings", "kimi_oauth_account_label", _("Kimi Code subscription"))
	# Connecting a subscription is the intent to use it: flip the auth mode so the
	# credential is not stored but silently ignored while the client stays on the
	# metered Open Platform key.
	set_value("Insights Settings", "moonshot_auth_mode", "Kimi Subscription")
	frappe.db.commit()


@frappe.whitelist()
def start_kimi_login() -> Dict[str, Any]:
	"""Request a device code for the Kimi Code subscription."""
	_guard()
	try:
		# This endpoint reads form parameters; a JSON body is rejected outright.
		response = requests.post(
			f"{_oauth_host()}/api/oauth/device_authorization",
			data={"client_id": CLIENT_ID},
			headers=_headers(),
			timeout=30,
		)
	except requests.RequestException as e:
		return {"success": False, "error": _("Cannot reach Kimi: {0}").format(str(e)[:200])}

	if response.status_code != 200:
		return {"success": False, "error": f"Kimi returned HTTP {response.status_code}: {response.text[:200]}"}

	data = response.json()
	device_code = data.get("device_code")
	user_code = data.get("user_code")
	if not device_code or not user_code:
		return {"success": False, "error": _("Kimi response was missing the device code fields.")}

	frappe.cache().set_value(PENDING_CACHE_KEY, {"device_code": device_code}, expires_in_sec=PENDING_TTL)

	return {
		"success": True,
		"user_code": user_code,
		"verification_url": data.get("verification_uri_complete") or data.get("verification_uri"),
		"interval": int(data.get("interval") or 5),
		"expires_in": int(data.get("expires_in") or PENDING_TTL),
	}


@frappe.whitelist()
def poll_kimi_login() -> Dict[str, Any]:
	"""Poll once for approval. The UI drives the retry cadence."""
	_guard()
	pending = frappe.cache().get_value(PENDING_CACHE_KEY)
	if not pending:
		return {"success": False, "status": "expired", "error": _("Start the login again — the code expired.")}

	try:
		response = requests.post(
			f"{_oauth_host()}/api/oauth/token",
			data={
				"client_id": CLIENT_ID,
				"device_code": pending["device_code"],
				"grant_type": DEVICE_GRANT,
			},
			headers=_headers(),
			timeout=30,
		)
	except requests.RequestException as e:
		return {"success": False, "status": "error", "error": str(e)[:200]}

	if response.status_code == 200:
		_persist(response.json())
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		return {"success": True, "status": "connected"}

	error = ""
	try:
		error = (response.json() or {}).get("error") or ""
	except Exception:
		pass

	if error in ("authorization_pending", "slow_down"):
		return {"success": False, "status": "pending"}
	if error in ("expired_token", "invalid_grant"):
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		return {"success": False, "status": "expired", "error": _("The code expired. Start again.")}
	if error == "access_denied":
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		return {"success": False, "status": "denied", "error": _("Authorization was denied.")}

	return {"success": False, "status": "error", "error": error or f"HTTP {response.status_code}"}


@frappe.whitelist()
def disconnect_kimi() -> Dict[str, Any]:
	"""Forget the stored subscription credential."""
	_guard()
	for field in ("kimi_oauth_access_token", "kimi_oauth_refresh_token", "kimi_oauth_account_label"):
		frappe.db.set_single_value("Insights Settings", field, "")
	frappe.db.set_single_value("Insights Settings", "kimi_oauth_expires_at", 0)
	frappe.db.commit()
	frappe.cache().delete_value(PENDING_CACHE_KEY)
	return {"success": True}


@frappe.whitelist()
def kimi_auth_status() -> Dict[str, Any]:
	"""Read-only view of the stored credential, never the token itself."""
	settings = frappe.get_single("Insights Settings")
	label = getattr(settings, "kimi_oauth_account_label", "") or ""
	expires_at = int(getattr(settings, "kimi_oauth_expires_at", 0) or 0)
	has_token = bool(settings.get_password("kimi_oauth_access_token", raise_exception=False))
	return {
		"connected": has_token,
		"account_label": label,
		"expires_at": expires_at,
		"expired": bool(expires_at and expires_at <= int(time.time())),
		"models": SUBSCRIPTION_MODELS,
	}


def _refresh(settings) -> Optional[str]:
	refresh_token = settings.get_password("kimi_oauth_refresh_token", raise_exception=False)
	if not refresh_token:
		return None
	try:
		response = requests.post(
			f"{_oauth_host()}/api/oauth/token",
			data={
				"client_id": CLIENT_ID,
				"grant_type": "refresh_token",
				"refresh_token": refresh_token,
			},
			headers=_headers(),
			timeout=30,
		)
	except requests.RequestException:
		return None
	if response.status_code != 200:
		return None
	tokens = response.json()
	tokens.setdefault("refresh_token", refresh_token)
	_persist(tokens)
	return tokens.get("access_token")


def get_access_token(settings=None) -> Optional[str]:
	"""Return a usable access token, refreshing shortly before expiry."""
	settings = settings or frappe.get_single("Insights Settings")
	token = settings.get_password("kimi_oauth_access_token", raise_exception=False)
	if not token:
		return None
	expires_at = int(getattr(settings, "kimi_oauth_expires_at", 0) or 0)
	if expires_at and expires_at - REFRESH_SKEW <= int(time.time()):
		return _refresh(settings) or token
	return token
