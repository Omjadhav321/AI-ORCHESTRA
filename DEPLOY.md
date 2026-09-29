# Deploying to InfinityFree

Pure static site — no PHP, no database, no build step. Everything runs in the browser.

## Folder layout

Upload the **contents** of this folder (not the folder itself) into `htdocs`.

```
sih new/                     <- upload these contents
├── index.html               entry page, links to the three portals
├── 404.html
├── .htaccess
├── DEPLOY.md
├── userside/
│   ├── index.html
│   ├── government office.jpg
│   └── hospital-building-illustration-....jpg
├── govoffice/
│   ├── index.html
│   └── kendra.jpg
└── hospitalside/
    └── index.html
```

## URLs after upload

| User type | URL |
|---|---|
| Entry page | `https://<your-account>.infinityfreeapp.com/` |
| Citizens & patients | `https://<your-account>.infinityfreeapp.com/userside/` |
| Government officers | `https://<your-account>.infinityfreeapp.com/govoffice/` |
| Hospital staff | `https://<your-account>.infinityfreeapp.com/hospitalside/` |

Each portal keeps its own session state, so opening one does not log you into another.

## Upload steps

1. Sign in at [infinityfree.com](https://infinityfree.com) and create a free account.
2. Create a hosting account. Choose any subdomain and `.infinityfreeapp.com` as the extension.
3. Open **Control Panel → File Manager** (or connect over FTP).
4. Open the `htdocs` folder.
5. Select everything in this local folder and upload it. Make sure the three portal
   folders land *inside* `htdocs`, not nested one level deeper.
6. Wait for the upload to finish, then open your subdomain.

The `.htaccess` file is hidden on Windows by default, so enable **View → Show → Hidden
items** before uploading, or it will be skipped. Without it the site still works — you
just get `/userside/index.html` instead of `/userside/`, and no custom 404 page.

### FTP instead of the file manager

```
Host:     ftp.infinityfree.com
Port:     21
Username: your InfinityFree username
Password: your account password
Remote:   /htdocs
```

## What the .htaccess does

- `DirectoryIndex` — serves each folder's `index.html` at the bare path
- 301 redirects `/userside` → `/userside/` and `/userside/index.html` → `/userside/`
- Custom `404.html` for dead links
- MIME types, UTF-8 charset, one week of caching for CSS/JS, one month for images
- gzip compression
- Directory listing off, `X-Powered-By` hidden
- Blocks direct access to `.md`, `.log`, `.ini`, `.sql`, `.bak` files

InfinityFree allows `.htaccess` but ignores anything it considers unsafe, so a missing
directive degrades quietly rather than erroring.

## Notes

- Google Fonts load from the CDN. The pages fall back to system fonts if blocked.
- The portals store mock data in the browser only. Nothing is sent to a server.
- The `sessionStorage` in `userside` keeps the citizen's place on refresh; closing the
  tab resets it. That is intended demo behaviour.

## Testing locally

No server needed — just open `index.html` directly. To preview with correct URLs:

```
php -S 127.0.0.1:8000 -t .
```

Then visit `http://127.0.0.1:8000/`.

Note that PHP's built-in server ignores `.htaccess`, so the pretty-URL redirects will not
fire locally. Test those after uploading.
