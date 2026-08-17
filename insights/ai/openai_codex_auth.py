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

DEVICE_CODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
REFRESH_URL = "https://auth.openai.com/oauth/token"
VERIFICATION_URL = "https://auth.openai.com/codex/device"
# The poll endpoint's 200 response is only an approval signal: it carries an
# intermediate `authorization_code` + server-issued PKCE `code_verifier`, not
# real tokens. Exchanging those at REFRESH_URL needs this fixed device-flow
# redirect_uri -- distinct from the (unused here) loopback browser flow's own
# redirect_uri. Verified against codex-rs/login/src/device_code_auth.rs
# (`complete_device_code_login`) and server.rs (`exchange_code_for_tokens`).
DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"

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


def _account_identity(*tokens: str) -> Dict[str, str]:
	"""Identity claims from whichever token carries them.

	Checked id_token first, then the access token -- both carry the same
	auth claim namespace, but a refresh response commonly omits id_token
	(see _refresh), so the access-token fallback keeps identity populated
	across refreshes rather than only on the first connect.
	"""
	account_id = plan = email = ""
	for token in tokens:
		if not token:
			continue
		claims = _decode_jwt_claims(token)
		auth = claims.get(AUTH_CLAIM_NS) or {}
		account_id = account_id or auth.get("chatgpt_account_id") or ""
		plan = plan or auth.get("chatgpt_plan_type") or ""
		email = email or claims.get("email") or ""
	return {"account_id": account_id, "plan": plan, "email": email}


def _stored_value(fieldname: str) -> str:
	"""Read a stored Insights Settings field back as plain text.

	Used to preserve identity/label across a refresh response that carries
	no usable claims, rather than blanking a healthy connection.
	"""
	return str(frappe.db.get_single_value("Insights Settings", fieldname) or "")


def _persist(tokens: Dict[str, Any]) -> Dict[str, str]:
	"""Store a freshly minted credential on Insights Settings."""
	access = tokens.get("access_token") or ""
	refresh = tokens.get("refresh_token") or ""
	id_token = tokens.get("id_token") or ""
	if not access:
		frappe.throw(_("OpenAI returned no access token."))

	identity = _account_identity(id_token, access)
	if not (identity["account_id"] or identity["email"]):
		# Neither token carried usable claims -- keep whatever identity is
		# already on file instead of blanking a healthy connection's label.
		identity["account_id"] = _stored_value("openai_oauth_account_id")

	# The token endpoint never returns `expires_in` (verified against the
	# Codex CLI's device/refresh contract) -- the access token's own `exp`
	# claim is the only real expiry source. Fall back to a conservative 1h
	# assumption only if that claim is somehow missing.
	exp_claim = _decode_jwt_claims(access).get("exp")
	expires_at = int(exp_claim) if isinstance(exp_claim, (int, float)) else int(time.time()) + 3600

	set_value = frappe.db.set_single_value
	set_value("Insights Settings", "openai_oauth_access_token", access)
	if refresh:
		set_value("Insights Settings", "openai_oauth_refresh_token", refresh)
	set_value("Insights Settings", "openai_oauth_account_id", identity["account_id"])
	set_value("Insights Settings", "openai_oauth_expires_at", expires_at)
	label = " · ".join(p for p in (identity["email"], identity["plan"]) if p)
	label = label or _stored_value("openai_oauth_account_label") or _("Connected")
	set_value("Insights Settings", "openai_oauth_account_label", label)
	# Connecting a subscription is the intent to use it; otherwise the credential
	# is stored but ignored while the client stays on the metered API key.
	set_value("Insights Settings", "openai_auth_mode", "ChatGPT Subscription")
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
			json={"client_id": CLIENT_ID},
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
		approval = response.json()
		auth_code = approval.get("authorization_code")
		code_verifier = approval.get("code_verifier")
		if not auth_code or not code_verifier:
			frappe.cache().delete_value(PENDING_CACHE_KEY)
			return {
				"success": False,
				"status": "error",
				"error": _("OpenAI approved the code but the response was missing the exchange fields."),
			}

		# Second hop: trade the approval for real tokens. Per the verified
		# contract this is form-encoded (unlike every other call here, which
		# is JSON) and uses the exact 5-field body order from server.rs.
		try:
			exchange = requests.post(
				REFRESH_URL,
				data={
					"grant_type": "authorization_code",
					"code": auth_code,
					"redirect_uri": DEVICE_REDIRECT_URI,
					"client_id": CLIENT_ID,
					"code_verifier": code_verifier,
				},
				headers={"Content-Type": "application/x-www-form-urlencoded"},
				timeout=30,
			)
		except requests.RequestException as e:
			return {"success": False, "status": "error", "error": str(e)[:200]}

		if exchange.status_code != 200:
			frappe.cache().delete_value(PENDING_CACHE_KEY)
			return {
				"success": False,
				"status": "error",
				"error": f"Token exchange failed with HTTP {exchange.status_code}: {exchange.text[:200]}",
			}

		identity = _persist(exchange.json())
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


def _clear_credential():
	"""Wipe the stored subscription credential.

	Shared by the interactive disconnect endpoint and a refresh that comes
	back with a confirmed-dead refresh token (HTTP 400/401) -- both cases
	mean the stored tokens are no longer usable.
	"""
	for field in (
		"openai_oauth_access_token",
		"openai_oauth_refresh_token",
		"openai_oauth_account_id",
		"openai_oauth_account_label",
	):
		frappe.db.set_single_value("Insights Settings", field, "")
	frappe.db.set_single_value("Insights Settings", "openai_oauth_expires_at", 0)
	frappe.db.commit()


@frappe.whitelist()
def disconnect_chatgpt() -> Dict[str, Any]:
	"""Forget the stored subscription credential."""
	_guard()
	_clear_credential()
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
			# Shape verified against the Codex CLI (codex-rs/login/src/auth/
			# manager.rs): a JSON body with no `scope` -- unlike the initial
			# device grant, omitting scope here preserves the original grant
			# per RFC 6749 s6 rather than narrowing it. The response never
			# carries `expires_in`; only the new access token's `exp` claim
			# says when it dies (handled in _persist).
			json={
				"client_id": CLIENT_ID,
				"grant_type": "refresh_token",
				"refresh_token": refresh_token,
			},
			headers={"Content-Type": "application/json"},
			timeout=30,
		)
	except requests.RequestException:
		# Transient network failure: keep the stored tokens so the next call
		# retries instead of forcing a reconnect.
		return None

	if response.status_code in (400, 401):
		# Refresh token revoked or expired -- unrecoverable without the user.
		_clear_credential()
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
	token = str(token) if token else None
	if not token:
		return None
	expires_at = int(getattr(settings, "openai_oauth_expires_at", 0) or 0)
	if expires_at and expires_at - REFRESH_SKEW <= int(time.time()):
		refreshed = _refresh(settings)
		if refreshed:
			return refreshed
		# Refresh failed. A confirmed-dead refresh token clears the stored
		# credential (see _refresh); serving the now-orphaned old token back
		# would only fail downstream with a raw 401 instead of the clean
		# "not connected" state the caller already handles.
		if frappe.db.get_single_value("Insights Settings", "openai_oauth_access_token"):
			return token
		return None
	return token
