# Customer Offline Activation Guide

Zenith Business ERP activates fully offline. No internet connection is required.

## 1. Get your request

Open the app. On first run the **Setup Wizard → License Activation** step (or later,
**Administration → License**) shows:

- **Full machine fingerprint** (64 characters) — copy it with **Copy full fingerprint**.
- **Save request file (.zreq)** — writes a small `PROFILE.zreq` file containing your
  fingerprint, selected profile, app version and date. It contains **no secrets**.

Send the `.zreq` file (or the copied fingerprint + your chosen profile) to your
vendor.

## 2. Receive your license

The vendor returns a `.zlic` license file (or a `ZBE1…` activation key). The license
is bound to your machine and your business profile.

## 3. Activate

On the same screen:

- **Import license file (.zlic)** — pick the file the vendor sent, **or**
- paste the `ZBE1…` activation key and click **Activate**.

You do not need to type the long key by hand when you have the `.zlic` file.

The app verifies the signature, that the license is for **this** computer, that the
profile matches, and that the dates are valid. Only then does activation succeed —
in the Setup Wizard the **Next** button enables only after a valid, matching license.

## 4. After activation

- The license is stored securely and survives restarts.
- A **Demo** license switches the app to read-only after it expires; your data is
  never deleted.
- If you change computers, ask the vendor for a **replacement** license (see the
  License page → Transfer request to get your new machine's request).

## Common messages

| Message | Meaning |
|---------|---------|
| This license belongs to a different computer | The `.zlic` was issued for another machine's fingerprint. |
| This license is for a different business profile | Wrong profile — request a license for your profile. |
| This license has expired | Ask the vendor to renew. |
| The license signature is invalid | The file was modified or is not genuine. |
