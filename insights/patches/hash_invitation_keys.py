import frappe

from insights.insights.doctype.insights_user_invitation.insights_user_invitation import hash_key


def execute():
	"""Replace every stored invitation key with its SHA-256 hash.

	Hashing in place keeps already-mailed links working: an incoming key
	hashes to what is now stored. Re-running is idempotent: a 64-character
	hex string is already a SHA-256 digest.
	"""
	invitations = frappe.get_all(
		"Insights User Invitation",
		filters={"key": ["is", "set"]},
		fields=["name", "key"],
	)
	for invitation in invitations:
		if len(invitation.key) == 64:
			continue
		frappe.db.set_value(
			"Insights User Invitation",
			invitation.name,
			"key",
			hash_key(invitation.key),
			update_modified=False,
		)
