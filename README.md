# Parcel IMAP Scan

A small Home Assistant custom integration for backfilling parcel tracking
numbers out of an existing mailbox.

Home Assistant's core `imap` integration only reacts to mail that looks
"new" from the moment it starts watching — it won't retroactively scan
historical messages already sitting in the inbox, even if you widen its
search criteria. This integration adds that missing piece: an on-demand
full-mailbox search, built on the Python standard library's `imaplib`
(not the third-party `imapclient` package, which has a known
incompatibility with Python 3.14 — see
[mjs/imapclient#618](https://github.com/mjs/imapclient/issues/618)).

## What it does

- Connects to your IMAP mailbox (tested against Gmail) with your own
  email address and an app password you create and enter yourself.
- On demand — via the `parcel_imap_scan.scan_now` service, or the
  "Scan inbox now" button this integration adds — searches the configured
  number of days back (default 90) across the whole mailbox, not just
  unread mail.
- Extracts tracking numbers for known carrier formats (Amazon Logistics,
  UPS, Royal Mail/Parcelforce, USPS, AliExpress/Cainiao, DHL, FedEx, DPD,
  Evri/Hermes, Yodel — see `extract.py`, which is written to be easy to
  extend with more patterns).
- Adds anything new to a Home Assistant to-do list (`todo.parcels` by
  default, configurable), skipping tracking numbers that are already
  present so repeated scans don't create duplicates.

## Installation

Via HACS as a custom repository, or by copying
`custom_components/parcel_imap_scan` into your Home Assistant
`custom_components` directory and restarting.

## Configuration

Settings → Devices & Services → Add Integration → "Parcel IMAP Scan".
You'll need:

- Your email address
- An **app password** for that account (not your normal login password —
  for Gmail, create one at <https://myaccount.google.com/apppasswords>,
  which requires 2-Step Verification to be enabled)
- IMAP server/port (defaults to `imap.gmail.com` / `993`)
- Folder to scan (default `INBOX`)
- Days back to search (default `90`)
- The to-do list entity to write into (default `todo.parcels`)

## Credentials

This integration never phones home or sends your credentials anywhere
but your own mail server over a direct TLS IMAP connection. Nobody but
you enters your password — that's the point of building it this way.
