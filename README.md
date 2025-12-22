# 🌐 Domain Expiration Monitor for Homepage

A beautiful domain expiration monitoring service for [Homepage](https://gethomepage.dev/) dashboard that tracks your domain renewals and alerts you before they expire.

![Domain Expiry Widget](screenshot.png)

## ✨ Features

- 🔴 **Visual Alerts** - Red indicator when domains are approaching expiration
- 📅 **Expiration Tracking** - Shows days remaining for each domain
- 🔄 **Auto-Refresh** - Configurable cache (default 6 hours)
- 🌍 **All TLDs** - Uses RDAP for universal domain support
- 🐳 **Docker Ready** - Simple container deployment
- ⚡ **Fast & Lightweight** - Python FastAPI backend
- 🎨 **Homepage Native** - Uses built-in customapi widget

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Running [Homepage](https://gethomepage.dev/) instance
- Domains you want to monitor

### Installation

1. **Create Project Directory**

```bash
mkdir -p /your/container/path/domain-expiry
cd /your/container/path/domain-expiry
```

2. **Create Configuration File** (`.env`)

```bash
cat > .env << EOF
DOMAINS=example.com,google.com,github.com
RDAP_BASE=https://rdap.org/domain
ALERT_DAYS=183
REFRESH_MINUTES=360
TZ=America/Denver
EOF
```

3. **Create Files**

Copy `app.py`, `requirements.txt`, `Dockerfile`, and `compose.yml` from this repository.

4. **Build and Start**

```bash
docker compose up -d --build
```

5. **Verify it's Running**

```bash
# Health check
curl http://localhost:8088/healthz

# Get domain status
curl http://localhost:8088/status
```

### Configure Homepage

Add to your `services.yaml`:

```yaml
- Domain Tools:
    - Domain Expirations:
        icon: mdi-web
        widget:
          type: customapi
          url: http://YOUR_SERVER_IP:8088/status
          display: dynamic-list
          refreshInterval: 900000  # 15 minutes
          mappings:
            items: domains
            name: domain
            label: label
```

**Replace `YOUR_SERVER_IP`** with your Docker host's IP address.

Restart Homepage:

```bash
docker compose restart homepage
```

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DOMAINS` | ✅ Yes | - | Comma-separated list of domains to monitor |
| `RDAP_BASE` | ✅ Yes | - | RDAP server URL (use `https://rdap.org/domain`) |
| `ALERT_DAYS` | ✅ Yes | - | Show alert when days remaining ≤ this value |
| `REFRESH_MINUTES` | No | 360 | Cache duration in minutes (6 hours) |
| `ALERT_EMOJI` | No | 🔴 | Emoji to show for expiring domains |
| `TZ` | No | UTC | Timezone (e.g., `America/New_York`) |
| `WHOIS_FALLBACK_ENABLED` | No | false | Fallback to WHOIS when RDAP fails (for ccTLDs) |

> **Note:** `WHOIS_FALLBACK_ENABLED` is useful for country-code TLDs (ccTLDs) that don't fully support RDAP yet. When enabled, the service will attempt a WHOIS lookup if RDAP fails. WHOIS is slower and being phased out globally, so this is intended as a temporary workaround.

### Example Configurations

**High-Security Setup** (check more frequently):
```bash
DOMAINS=banking.com,payment.com
ALERT_DAYS=90
REFRESH_MINUTES=60  # 1 hour
```

**Personal Domains** (longer cache):
```bash
DOMAINS=myblog.com,portfolio.io,family.name
ALERT_DAYS=183
REFRESH_MINUTES=720  # 12 hours
```

## 📡 API Endpoints

### `GET /status`

Returns full domain information with metadata.

**Query Parameters:**
- `force=true` - Force refresh cache

**Response:**
```json
{
  "updated": "2024-12-21T16:30:00Z",
  "domains": [
    {
      "domain": "example.com",
      "expires": "2025-06-15T00:00:00Z",
      "expires_us": "06/15/2025",
      "days_left": 176,
      "label": "06/15/2025 (176d)",
      "alert": false,
      "source": "https://rdap.org/domain/example.com"
    }
  ],
  "refresh_minutes": 360,
  "alert_days": 183,
  "rdap_base": "https://rdap.org/domain"
}
```

### `GET /flat`

Returns simplified text-based format.

**Response:**
```json
{
  "line1": "example.com — Exp: 06/15/2025 (176d)",
  "line2": "🔴 urgent.com — Exp: 🔴 01/10/2025 (20d)",
  "updated": "2024-12-21T16:30:00Z"
}
```

### `GET /healthz`

Health check endpoint for monitoring.

**Response:**
```json
{
  "ok": true
}
```

## 🎨 Display Options

### Dynamic List (Recommended)

Shows all domains in a clean list:
```yaml
widget:
  type: customapi
  url: http://IP:8088/status
  display: dynamic-list
  mappings:
    items: domains
    name: domain
    label: label
```

### Block Display

For 1-4 domains:
```yaml
widget:
  type: customapi
  url: http://IP:8088/flat
  display: block
  mappings:
    - field: line1
      label: Primary Domain
    - field: line2
      label: Backup Domain
```


## 🔧 Troubleshooting

### Widget Shows "Error" or "N/A"

1. **Check Container Logs**
   ```bash
   docker logs domain-expiry
   ```

2. **Verify API is Accessible**
   ```bash
   curl http://YOUR_IP:8088/status
   ```

3. **Test Individual Domain**
   ```bash
   curl "https://rdap.org/domain/example.com"
   ```

### Domains Not Updating

- **Force Refresh**: `curl "http://YOUR_IP:8088/status?force=true"`
- **Reduce Cache**: Lower `REFRESH_MINUTES` in `.env`
- **Restart Container**: `docker compose restart`

### "No Expiration in RDAP" Error

Some domains/TLDs don't provide expiration data via RDAP:

**Solution: Enable WHOIS Fallback**
1. Add to your `.env` file:
   ```bash
   WHOIS_FALLBACK_ENABLED=true
   ```
2. Restart container: `docker compose restart`
3. Check logs: `docker logs domain-expiry`

This is particularly useful for:
- Country-code TLDs (ccTLDs) like `.bz`, `.ai`, `.io` that haven't fully adopted RDAP
- Legacy domains on older registries
- Domains transitioning to RDAP support

**Note:** WHOIS lookups are slower and less reliable than RDAP. This is intended as a temporary workaround while global RDAP adoption continues.

### Homepage Can't Connect

1. **Use Host IP, Not localhost**
   - ❌ `http://localhost:8088`
   - ✅ `http://192.168.1.100:8088`

2. **Check Docker Network**
   ```bash
   docker network inspect bridge
   ```

3. **Verify Port is Open**
   ```bash
   netstat -tulpn | grep 8088
   ```

## 💡 Tips & Best Practices

### Security

- 🔒 Don't expose port 8088 to the internet
- 🛡️ Run behind reverse proxy with auth if needed
- 📝 No sensitive data is stored
- 🔑 RDAP queries don't require authentication

### Performance

- 📊 Monitor 10-20 domains max per instance
- ⏱️ Keep cache at 6+ hours to respect RDAP servers
- 🚀 Use CDN RDAP (`rdap.org`) for best performance
- 💾 Container uses minimal resources (~50MB RAM)

### Maintenance

- 🔄 Update container regularly: `docker compose pull && docker compose up -d`
- 📅 Review alert threshold quarterly
- 🧹 Check logs occasionally: `docker logs domain-expiry --tail 100`

## 🤔 FAQ

**Q: Can I monitor subdomains?**  
A: No - expiration is tracked at the domain level only. Subdomains inherit the parent domain's expiration.

**Q: What about private/internal domains?**  
A: RDAP only works for publicly registered domains. Internal domains won't work.

**Q: Can I use multiple RDAP providers?**  
A: Currently no, but you could run multiple instances with different providers.

**Q: Why 6 hour cache?**  
A: Domain expiry dates change rarely. Shorter cache = unnecessary load on RDAP servers.

**Q: Can I get notifications?**  
A: Not yet - see roadmap below. For now, Homepage is your notification.

**Q: Does this work with Homepage v0.8.x?**  
A: Yes! The `customapi` widget has been available for a long time.

**Q: How many domains can I monitor?**  
A: Tested up to 50. More than that, consider multiple instances or longer cache times.

## 🗺️ Roadmap

Potential future features (PRs welcome!):

- [ ] Webhook notifications (Discord, Slack, email)
- [ ] SSL certificate expiry monitoring
- [ ] DNS record monitoring
- [ ] Historical data/trends
- [ ] Web UI for configuration
- [ ] Multiple RDAP provider support
- [ ] Prometheus metrics export
- [ ] Persistent cache across restarts
- [ ] Auto-renewal reminders
- [ ] Import domains from file

## 🤝 Contributing

Contributions welcome! Ideas:

1. **Report Issues** - Found a bug? Open an issue
2. **Feature Requests** - Have an idea? Start a discussion
3. **Code** - PRs welcome for features or fixes
4. **Documentation** - Improve README, add examples
5. **Testing** - Test with different TLDs and report back

## 📚 Related Projects

- [Homepage](https://gethomepage.dev/) - The dashboard this integrates with
- [RDAP](https://www.icann.org/rdap) - Domain registration data protocol
- [Whois](https://en.wikipedia.org/wiki/WHOIS) - Alternative domain lookup

## 📄 License

GPL-3.0 License - see LICENSE file

## 🙏 Acknowledgments

- Homepage team for excellent dashboard & customapi widget
- RDAP.org for free RDAP meta-service
- FastAPI for the awesome Python framework

## 📞 Support

- 🐛 [Open an Issue](https://github.com/Hackpig1974/domain-expiry/issues)
- 💬 [Discussions](https://github.com/Hackpig1974/domain-expiry/discussions)
- ⭐ Star this repo if you find it useful!

---

Made with ❤️ for the homelab community
