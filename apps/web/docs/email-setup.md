# Email setup — OrigenLab (contacto@origenlab.cl)

**Source of truth:** Titan is the primary mailbox provider for the domain origenlab.cl. Do not treat HostGator/cPanel webmail as the main system for this address.

**Checklist de despliegue del sitio:** [deployment.md](deployment.md) remite aquí para comprobar que **contacto@** funciona; el sitio estático y el DNS pueden vivir en HostGator sin que el buzón se gestione como “correo cPanel”.

---

## Primary configuration

| Item | Value |
|------|--------|
| Email address | contacto@origenlab.cl |
| Mailbox provider | Titan |
| Webmail | Titan webmail (works) |

---

## IMAP / SMTP (for Outlook and other clients)

Use Titan’s servers. Do not use `mail.origenlab.cl` or HostGator mail servers for this address.

| Setting | Value |
|---------|--------|
| **Incoming (IMAP)** | |
| Server | imap.titan.email |
| Port | 993 |
| Security | SSL/TLS |
| **Outgoing (SMTP)** | |
| Server | smtp.titan.email |
| Port | 465 |
| Security | SSL/TLS |
| Username | contacto@origenlab.cl |
| Password | [Use the mailbox password; do not store in docs] |

- Third-party / external app access must be enabled in the Titan account for IMAP/SMTP to work.
- SMTP password is the same as the mailbox password (store securely; not in repo).

---

## DKIM (Titan)

- **Verified Titan DKIM selector:** `titan1._domainkey`
- DNS also has `default._domainkey`; leave it unless a future migration requires review.
- A duplicate TXT record for the same selector was removed to fix DKIM; do not add duplicate DKIM records.
- DKIM status is verified in Titan and email reputation.

---

## Operational reminders

1. **DNS:** Nameservers are HostGator (`ns00010.hostgator.cl`, `ns00011.hostgator.cl`). Do not change DNS casually; the site and email depend on current DNS.
2. **Sent Items:** After configuring Outlook (or any client), verify that sent messages are saved to Sent Items; historical sent quotes are business-critical.
3. **Send/receive test:** After any change (DNS, client config, Titan settings), test both sending and receiving.

---

## Troubleshooting

| Problem | Notes |
|--------|--------|
| Sending fails | Ensure DKIM is verified and there are no duplicate TXT records for `titan1._domainkey`. Use Titan’s IMAP/SMTP servers, not HostGator or `mail.origenlab.cl`. |
| Outlook auto-detect wrong | Outlook may suggest `mail.origenlab.cl`. Ignore it; use `imap.titan.email` and `smtp.titan.email` with the ports and security above. |
| External app access | In Titan, enable access for external/third-party apps (IMAP/SMTP) or clients will not connect. |

---

## Recovery / credentials (placeholders)

- **Mailbox password:** Stored securely outside the repo. Not documented here.
- **Titan account recovery:** [Pending confirmation: recovery method and contact]
- **Domain/hosting access:** HostGator/cPanel credentials kept separately; not in repo.
