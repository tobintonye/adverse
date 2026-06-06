# Frontend Implementation Summary

## Phase 1 — Auth Flow Updates

- **Registration** now has a role selection (Advertiser / Ad Manager) with styled radio cards
- **Post-login redirect** is role-aware:
  - Advertisers → Advertiser dashboard
  - Ad Managers → Ad Manager dashboard
  - Admins → Admin panel
- **Post-email-verification redirect** routes to the correct profile creation page based on role
- **Change Password** screen added at `/adverse-auth/change-password/`, linked from Settings in all three roles

---

## Phase 2 — Ad Manager Screens

| URL | Screen |
| --- | --- |
| `admanager/dashboard/` | Stats cards + quick links (filled in) |
| `admanager/settings/` | Profile edit + Change Password link (filled in) |
| `admanager/billboards/` | Billboard table with availability status badges |
| `admanager/billboards/add/` | Add billboard form |
| `admanager/billboards/<pk>/edit/` | Edit billboard (reuses same form template) |
| `admanager/campaign-requests/` | Pending campaign requests list |
| `admanager/campaign-requests/<pk>/` | Campaign detail with Approve / Reject + reason field |

---

## Phase 3 — Advertiser Screens

| URL | Screen |
| --- | --- |
| `advertiser/profile/` | One-time profile creation (shown after email verification) |
| `advertiser/dashboard/` | Stats + recent media + quick action cards |
| `advertiser/billboards/` | Browse available billboards with screen type / price filters |
| `advertiser/media/` | Media library with status badges (Pending / Admin Approved / Fully Approved / Rejected) |
| `advertiser/media/upload/` | File upload form with media type toggle (hides duration field for images) |
| `advertiser/campaigns/` | Campaign list with status badges |
| `advertiser/campaigns/create/` | Campaign creation: select media, billboards, schedule, budget |
| `advertiser/campaigns/<pk>/` | Campaign detail with Submit / Cancel actions and rejection reason display |
| `advertiser/settings/` | Profile edit + Change Password link |

---

## Phase 4 — Admin Panel Screens

| URL | Screen |
| --- | --- |
| `admin-panel/` | Overview with pending counts (Advertisers / Media / Campaigns) |
| `admin-panel/advertisers/` | All advertisers table with Verify / Suspend inline actions |
| `admin-panel/media/` | Pending media list with Approve / Reject + reason field |
| `admin-panel/campaigns/` | Pending campaigns list |
| `admin-panel/campaigns/<pk>/` | Full campaign detail with Forward to Manager / Reject actions |

---

## Design System (all screens)

| Token | Value |
| --- | --- |
| Background | `bg-black` |
| Sidebar / Cards | `bg-zinc-950` / `bg-zinc-900` |
| Borders | `border-zinc-800` |
| Primary action | `bg-red-600 hover:bg-red-700` |
| Active nav link | `text-white bg-zinc-800` |
| Pending badge | `bg-yellow-900/30 text-yellow-400` |
| Approved badge | `bg-green-900/30 text-green-400` |
| Rejected badge | `bg-red-900/30 text-red-400` |
| Active badge | `bg-blue-900/30 text-blue-400` |
| Font | Inter (Google Fonts) + Tailwind CDN |

---

## New Files Created

### Python

- `advertiser/decorators.py` — `@advertiser_required`
- `advertiser/forms.py` — `AdvertiserProfileForm`, `MediaUploadForm`, `CampaignForm`
- `advertiser/views.py` — all template views
- `advertiser/urls.py`
- `admanager/forms.py` — added `BillboardForm`
- `admin_panel/` — full Django app (views, urls, decorators)

### Templates

- `templates/security/change_password.html`
- `templates/adManager/base.html`, `dashboard.html`, `settings.html`, `billboard_list.html`, `billboard_form.html`, `campaign_requests.html`, `campaign_request_detail.html`
- `templates/advertiser/base.html`, `profile.html`, `dashboard.html`, `billboard_browse.html`, `media_list.html`, `media_upload.html`, `campaign_list.html`, `campaign_create.html`, `campaign_detail.html`, `settings.html`
- `templates/admin_panel/base.html`, `dashboard.html`, `advertisers.html`, `media.html`, `campaigns.html`, `campaign_detail.html`

### Modified

- `security/views.py` — role-based redirects, change password view
- `security/urls.py` — change-password route
- `templates/security/register.html` — role selection UI
- `admanager/views.py` — billboard + campaign request views
- `admanager/urls.py` — new routes
- `adverseproject/urls.py` — include advertiser + admin\_panel URLs
- `adverseproject/settings.py` — added `admin_panel` to `INSTALLED_APPS`
