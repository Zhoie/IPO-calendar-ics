# 📈 IPO Calendar (.ics Generator)

This project automatically creates an **.ics** file that lists upcoming — and very recent — U.S. IPOs, using data from the [Finnhub API](https://finnhub.io/).  
The file is refreshed **twice daily** by GitHub Actions, so you can subscribe in any calendar app (Apple Calendar, Google Calendar, Outlook, etc.) and never miss a new listing.

---

## ✨ Features

| Feature | Details |
|---------|---------|
| **Coverage** | Past 15 days **+** next 30 days of IPOs (free-tier limit) |
| **Data points** | Company name, ticker, exchange, share count, price range |
| **All-day events** | Easier to view; time-zone aware (ET) |
| **Formatted numbers** | `23 M` shares, `$15–17` price range, etc. |
| **Auto-publish** | GitHub Actions commits `ipo_calendar.ics` back to the repo |
| **One-click subscribe** | Raw URL works in iOS/macOS/Google/Outlook |

---

## 🚀 Quick Start

### 1 · Fork or Clone the Repo

```bash
git clone https://github.com/<your-username>/IPO-CALENDAR-ICS.git
cd IPO-CALENDAR-ICS
