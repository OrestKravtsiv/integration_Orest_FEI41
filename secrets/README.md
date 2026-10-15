# Provisioning local Compose secrets

The Compose setup requires two local files in this directory:

- `db_password` — PostgreSQL password shared with Orders API.
- `jwt_secret_key` — HS256 signing key used only by Orders API.

The `*.example` files are placeholders, not credentials. Do not use them as
secret values and do not commit the real secret files.

## Generate secrets on Linux or WSL

From the repository root:

```bash
umask 077
openssl rand -hex 32 > secrets/db_password
openssl rand -hex 48 > secrets/jwt_secret_key
chmod 600 secrets/db_password secrets/jwt_secret_key
```

Each command overwrites the target file. Back up secrets securely before
regenerating them for an existing deployment: changing the PostgreSQL password
file does not change the password stored in an initialized database, and
replacing the JWT key invalidates previously issued tokens after Orders API is
restarted.

For native Windows, protect the files with restrictive NTFS ACLs. POSIX mode
`0600` applies to Linux/WSL; when running the lab through WSL, keep the files in
the Linux filesystem and run Docker Compose from the repository there.

Compose mounts the files read-only at `/run/secrets/db_password` and
`/run/secrets/jwt_secret_key`. A missing or empty required secret prevents
Orders API startup (and a missing database secret prevents PostgreSQL startup).
