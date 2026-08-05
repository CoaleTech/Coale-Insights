# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""ChatGPT Plus/Pro (Codex) subscription auth for the OpenAI provider.

Uses OpenAI's device-authorization flow, which needs no loopback callback and
is therefore the only OAuth variant that works on a headless Frappe host:

    1. POST /api/accounts/deviceauth/usercode  -> device_auth_id + user_code
    2. operator approves at auth.openai.com/codex/device
    3. POST /api/accounts/deviceauth/token     -> access + refresh + id token
       (returns 403 `deviceauth_authorization_pending` until step 2 completes)

The resulting credential bills against the ChatGPT subscription rather than a
metered API key, but it is *not* interchangeable with one: subscription traffic
must go to the ChatGPT backend, not api.openai.com. See `openai_client.py`.
"""

import base64
import json
import time
from typing import Any, Dict, Optional

import frappe
import requests
from frappe import _

# Public Codex client id, as used by the Codex CLI device flow.
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
SCOPE = "openid profile email offline_access"

DEVICE_CODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
REFRESH_URL = "https://auth.openai.com/oauth/token"
VERIFICATION_URL = "https://auth.openai.com/codex/device"

# id_token claim namespace carrying the ChatGPT account id / plan.
AUTH_CLAIM_NS = "https://api.openai.com/auth"

PENDING_CACHE_KEY = "insights:openai_codex_device_login"
PENDING_TTL = 900  # device codes expire well inside 15 minutes
REFRESH_SKEW = 120  # refresh this many seconds before nominal expiry


def _guard():
	"""Only someone who may edit the settings may move the credential."""
	frappe.has_permission("Insights Settings", "write", throw=True)


def _decode_jwt_claims(token: str) -> Dict[str, Any]:
	"""Read claims out of our own id_token. Not a signature check."""
	try:
		payload = token.split(".")[1]
		payload += "=" * (-len(payload) % 4)
		return json.loads(base64.urlsafe_b64decode(payload))
	except Exception:
		return {}


def _account_identity(id_token: str) -> Dict[str, str]:
	claims = _decode_jwt_claims(id_token)
	auth = claims.get(AUTH_CLAIM_NS) or {}
	return {
		"account_id": auth.get("chatgpt_account_id") or "",
		"plan": auth.get("chatgpt_plan_type") or "",
		"email": claims.get("email") or "",
	}


def _persist(tokens: Dict[str, Any]) -> Dict[str, str]:
	"""Store a freshly minted credential on Insights Settings."""
	access = tokens.get("access_token") or ""
	refresh = tokens.get("refresh_token") or ""
	id_token = tokens.get("id_token") or ""
	if not access:
		frappe.throw(_("OpenAI returned no access token."))

	identity = _account_identity(id_token)
	expires_in = int(tokens.get("expires_in") or 3600)

	set_value = frappe.db.set_single_value
	set_value("Insights Settings", "openai_oauth_access_token", access)
	if refresh:
		set_value("Insights Settings", "openai_oauth_refresh_token", refresh)
	set_value("Insights Settings", "openai_oauth_account_id", identity["account_id"])
	set_value("Insights Settings", "openai_oauth_expires_at", int(time.time()) + expires_in)
	label = " · ".join(p for p in (identity["email"], identity["plan"]) if p)
	set_value("Insights Settings", "openai_oauth_account_label", label or _("Connected"))
	frappe.db.commit()
	return identity


@frappe.whitelist()
def start_chatgpt_login() -> Dict[str, Any]:
	"""Request a device code and hand the operator a code to approve."""
	_guard()
	try:
		response = requests.post(
			DEVICE_CODE_URL,
			# This endpoint rejects form encoding; it wants a JSON body.
			json={"client_id": CLIENT_ID, "scope": SCOPE},
			headers={"Content-Type": "application/json"},
			timeout=30,
		)
	except requests.RequestException as e:
		return {"success": False, "error": _("Cannot reach OpenAI: {0}").format(str(e)[:200])}

	if response.status_code != 200:
		return {"success": False, "error": f"OpenAI returned HTTP {response.status_code}: {response.text[:200]}"}

	data = response.json()
	device_auth_id = data.get("device_auth_id")
	user_code = data.get("user_code")
	if not device_auth_id or not user_code:
		return {"success": False, "error": _("OpenAI response was missing the device code fields.")}

	frappe.cache().set_value(
		PENDING_CACHE_KEY,
		{"device_auth_id": device_auth_id, "user_code": user_code},
		expires_in_sec=PENDING_TTL,
	)

	return {
		"success": True,
		"user_code": user_code,
		"verification_url": VERIFICATION_URL,
		"interval": int(data.get("interval") or 5),
		"expires_at": data.get("expires_at"),
	}


@frappe.whitelist()
def poll_chatgpt_login() -> Dict[str, Any]:
	"""Poll once for approval. The UI drives the retry cadence."""
	_guard()
	pending = frappe.cache().get_value(PENDING_CACHE_KEY)
	if not pending:
		return {"success": False, "status": "expired", "error": _("Start the login again — the code expired.")}

	try:
		response = requests.post(
			DEVICE_TOKEN_URL,
			json={
				"client_id": CLIENT_ID,
				"device_auth_id": pending["device_auth_id"],
				# The token endpoint requires the user code alongside the id.
				"user_code": pending["user_code"],
			},
			headers={"Content-Type": "application/json"},
			timeout=30,
		)
	except requests.RequestException as e:
		return {"success": False, "status": "error", "error": str(e)[:200]}

	if response.status_code == 200:
		identity = _persist(response.json())
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		return {"success": True, "status": "connected", "account": identity}

	body = {}
	try:
		body = response.json().get("error") or {}
	except Exception:
		pass
	code = body.get("code") or ""

	if code == "deviceauth_authorization_pending":
		return {"success": False, "status": "pending"}
	if code in ("deviceauth_expired", "expired_token"):
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		return {"success": False, "status": "expired", "error": _("The code expired. Start again.")}
	if code in ("deviceauth_denied", "access_denied"):
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		return {"success": False, "status": "denied", "error": _("Authorization was denied.")}

	return {
		"success": False,
		"status": "error",
		"error": body.get("message") or f"HTTP {response.status_code}",
	}


@frappe.whitelist()
def disconnect_chatgpt() -> Dict[str, Any]:
	"""Forget the stored subscription credential."""
	_guard()
	for field in (
		"openai_oauth_access_token",
		"openai_oauth_refresh_token",
		"openai_oauth_account_id",
		"openai_oauth_account_label",
	):
		frappe.db.set_single_value("Insights Settings", field, "")
	frappe.db.set_single_value("Insights Settings", "openai_oauth_expires_at", 0)
	frappe.db.commit()
	frappe.cache().delete_value(PENDING_CACHE_KEY)
	return {"success": True}


@frappe.whitelist()
def chatgpt_auth_status() -> Dict[str, Any]:
	"""Read-only view of the stored credential, never the token itself."""
	settings = frappe.get_single("Insights Settings")
	account_id = getattr(settings, "openai_oauth_account_id", "") or ""
	expires_at = int(getattr(settings, "openai_oauth_expires_at", 0) or 0)
	return {
		"connected": bool(account_id),
		"account_label": getattr(settings, "openai_oauth_account_label", "") or "",
		"account_id": account_id,
		"expires_at": expires_at,
		"expired": bool(expires_at and expires_at <= int(time.time())),
	}


def _refresh(settings) -> Optional[str]:
	refresh_token = settings.get_password("openai_oauth_refresh_token", raise_exception=False)
	if not refresh_token:
		return None
	try:
		response = requests.post(
			REFRESH_URL,
			json={
				"client_id": CLIENT_ID,
				"grant_type": "refresh_token",
				"refresh_token": refresh_token,
				"scope": SCOPE,
			},
			headers={"Content-Type": "application/json"},
			timeout=30,
		)
	except requests.RequestException:
		return None
	if response.status_code != 200:
		return None
	tokens = response.json()
	# A refresh may omit the refresh token; keep the existing one in that case.
	tokens.setdefault("refresh_token", refresh_token)
	_persist(tokens)
	return tokens.get("access_token")


def get_access_token(settings=None) -> Optional[str]:
	"""Return a usable access token, refreshing shortly before expiry."""
	settings = settings or frappe.get_single("Insights Settings")
	token = settings.get_password("openai_oauth_access_token", raise_exception=False)
	if not token:
		return None
	expires_at = int(getattr(settings, "openai_oauth_expires_at", 0) or 0)
	if expires_at and expires_at - REFRESH_SKEW <= int(time.time()):
		return _refresh(settings) or token
	return token
