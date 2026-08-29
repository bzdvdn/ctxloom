# Authentication

The platform uses two sign-in mechanisms: access tokens and enterprise SSO.
Both issue a short-lived token valid for 24 hours.

## Access tokens

A user receives a token after signing in through SSO or manually in the
personal account. The token is attached to every request in the header:

```
Authorization: Bearer <token>
```

Tokens are issued by the authorization service; they can be revoked at any
time — after revocation, signing in again requires new verification.

## SSO

For enterprise accounts, sign-in works through a single entry point (SSO).
An administrator connects their provider (for example, SAML or OIDC) in the
organization settings. After that, users sign in without separate passwords.

## Roles and access

Access to the console and API differs by role:

- operator — view projects and tasks;
- engineer — edit projects, run calculations;
- administrator — manage roles, integrations, and limits.

Role checks run on every request: a role change or token revocation applies
immediately, without waiting for the session to end.

## FAQ

- Token expired — sign in again through SSO.
- Need access for a plugin — create a system key in the "System accounts"
  section; such keys are not tied to a person.
- Lost access — the organization administrator can revoke all of a user's
  tokens in one action.