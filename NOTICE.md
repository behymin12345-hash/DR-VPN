# NOTICE — DR-VPN

DR-VPN is a fork of **PasarGuard** (https://github.com/PasarGuard/panel), which in turn
is derived from **Marzban** (https://github.com/Gozargah/Marzban).

## License

DR-VPN is licensed under the **GNU Affero General Public License v3.0** (see `LICENSE`),
inherited from upstream. The original license document and its copyright notice
("Copyright (C) 2025 PasarGuard organization.") are preserved unmodified.

Additional copyright for the DR-VPN modifications: Copyright (C) 2025 DR-VPN contributors.

## Attribution obligations

- The PasarGuard and Marzban upstream projects retain all credit for the original codebase.
- Under AGPL-3.0 §13, if you run a modified version of this software as a network service,
  you must offer its Corresponding Source to the users of that service.
- The upstream documentation (https://docs.pasarguard.org) is referenced transiently from the
  dashboard help links until DR-VPN-specific documentation becomes available.

## Third-party components

All upstream dependencies (Python packages in `pyproject.toml`, npm packages in
`dashboard/package.json`, and the external `pasarguard-node` Go binary) remain governed by
their own licenses. Wire-level identifiers (NATS subjects/buckets, API-key prefix, token
formats) are kept unchanged on purpose for compatibility with the upstream node bridge.
