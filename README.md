<pre style="color: #246;">
   ▒█▀▀▀█ █▀▄▀█ █░░█ ▀▀█▀▀ █▀▀ █▀▀ █▀▀█ █▀▀█ █▀▀█ █▀▀ 
   ░▀▀▀▄▄ █░▀░█ █░░█ ░░█░░ ▀▀█ █░░ █▄▄▀ █▄▄█ █░░█ █▀▀ 
   ▒█▄▄▄█ ▀░░░▀ ░▀▀▀ ░░▀░░ ▀▀▀ ▀▀▀ ▀░▀▀ ▀░░▀ █▀▀▀ ▀▀▀ 
</pre>

# _Securing smut to salty pervs over CLI_ 🍆💦

A Python-based tool to scrape and download adult content from various websites straight to your preferred data store, alongside `.nfo` files that preserve the title, tags, actors, studios, and other metadata for a richer immediate watching experience in [Plex](https://plex.tv), [Jellyfin](https://github.com/jellyfin/jellyfin), or [Stash](https://github.com/stashapp).

---

## Requirements 🧰

- Python 3.10+ 🐍
- Recommended: [Conda](https://github.com/conda/conda) or [Mamba](https://github.com/mamba-org/mamba) for environment management 🐼
- For JavaScript-heavy sites: [Selenium](https://pypi.org/project/selenium/) + [Chromedriver](https://chromedriver.chromium.org/) for JS-heavy sites, and [webdriver-manager](https://pypi.org/project/webdriver-manager/) for foolproof ChromeDriver management.
- [ffmpeg](https://ffmpeg.org/) for downloading from certain sites that use HLS and aren't supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp).
- Dozen or so Python libraries in [requirements.txt](https://codeberg.org/smutscrape/smutscrape/blob/main/requirements.txt).

All Python dependencies are in `requirements.txt`.

---

## Installation 🛠️

1. **Clone the Repo 📂**

   ```bash
   git clone https://codeberg.org/smutscrape/smutscrape.git
   cd smutscrape
   ```

2. **Install Dependencies 🚀**

   ```bash
   # With Conda (Recommended):
   conda create -n smutscrape python=3.10.13
   conda activate smutscrape
   pip install -r requirements.txt

   # With pip:
   pip3 install -r requirements.txt
   ```

   Install additional tools:

   ```bash
   # On Ubuntu/Debian
   sudo apt-get install yt-dlp wget curl ffmpeg chromium
   # On macOS with Homebrew
   brew install yt-dlp wget curl ffmpeg google-chrome
   ```

   For Selenium (not required for all sites):

   ```bash
   # webdriver-manager is the best solution for most people:
   pip install webdriver-manager
   # ... but a manual chromedriver installation may be necessary for some setups:
   brew install chromedriver
   ```

   For Cloudflare evasion:
   ```bash
   pip install --upgrade --force-reinstall --no-cache yt-dlp curl_cffi
   ```

3. **Configure `config.yaml` ⚙️**

   ```bash
   cp example-config.yaml config.yaml
   nano config.yaml
   ```

   Set up `download_destinations`, `ignored` terms, `selenium` paths, and optional `vpn` integration for secure, anonymous scraping.

4. **Make Executable ⚡️**

   ```bash
   chmod +x scrape.py
   # Optional: add a symlink for easy use from anywhere
   sudo ln -s $(realpath ./scrape.py) /usr/local/bin/scrape
   ```

---

## Usage 🚀

Run `python scrape.py` (or `scrape` if symlinked) to download adult content and save metadata in `.nfo` files. With no arguments, you'll get a detailed, aesthetic readout of all supported site modes on your system, dynamically generated from `./sites/` configurations (see left image below). Alternatively, running `scrape {code}` (e.g., `scrape ml`) provides detailed info about that site—curated notes, tips, caveats, available metadata, special requirements, and usage examples (see right image below).

<div style="display: flex; justify-content: center; align-items: center; gap: 20px; padding: 10px;"><a href="https://codeberg.org/smutscrape/smutscrape/raw/main/screenshots/screenshot1.jpg"><img src="https://github.com/smutscrape/smutscrape/raw/main/screenshots/screenshot1.jpg?raw=true" alt="No Arguments Screenshot" width="300" style="border: 2px solid #ff69b4; border-radius: 5px;"></a> <a href="https://github.com/smutscrape/smutscrape/raw/main/screenshots/screenshot2.jpg?"><img src="https://github.com/smutscrape/smutscrape/raw/main/screenshots/screenshot2.jpg?raw=true" alt="Site Identifier Screenshot" width="300" style="border: 2px solid #ff69b4; border-radius: 5px;"></a></div>

---

### To start scraping, build commands following this basic syntax:

```
      scrape {code} {mode} {query}
``` 

### Supported sites and modes:

Refer to this table of supported sites with available modes and metadata, or see the current configuration with latest updates by simply running `scrape` without arguments.

| code   | site                          | modes                          | metadata                       |
| ------ | ----------------------------- | ------------------------------ | ------------------------------ |
| `11v`  | **_11Vids_** †                | video · search · tag ✦ · category | actors · categories · description · studios · tags |
| `9v`   | **_9Vids_** †                 | video · search · tag           | description · tags             |
| `bsip` | **_BrotherSisterIncestPorn_** | video · all ✦                  | None                           |
| `fdpis` | **_FatherDaughterPornIncestSex_** | video · all ✦                  | None                           |
| `fphd` | **_FamilyPornHD_** †          | video · tag ✦ · model ✦ · search ✦ · studio ✦ · rss | actors · description · studios · tags |
| `fptv` | **_FamilyPorn_** †            | video · model · tag · search · studio | actors · description · studios · tags |
| `fs`   | **_Family Sex_** †            | video · tag ✦ · search · model ✦ | actors · description · studios · tags |
| `fsv`  | **_FamilySexVideos_** †       | video · search                 | None                           |
| `fsx`  | **_ForcedSex_**               | video · all ✦                  | None                           |
| `if`   | **_IncestFlix_**              | video · tag ✦‡                 | actors · studios · tags        |
| `ig`   | **_IncestGuru_**              | video · tag ✦                  | actors · studios · tags        |
| `il`   | **_IncestLover_**             | video · all ✦                  | None                           |
| `lf`   | **_LoneFun_**                 | video · search ✦               | description · tags             |
| `lux`  | **_Luxure_**                  | video · search ✦ · channel     | description · tags             |
| `lv`   | **_LeakVids_** †              | video · search · tag · category | actors · description · studios · tags |
| `ml`   | **_Motherless_** †            | video · search ✦ · tag ✦ · user ✦ · group ✦ · group_code ✦ | tags                           |
| `msip` | **_MomSonIncestPorn_**        | video · all ✦                  | None                           |
| `ph`   | **_PornHub_** †               | video · model ✦ · category ✦ · tag ✦ · studio ✦ · search ✦ · pornstar ✦ | actors · code · date · studios · tags |
| `rip`  | **_RapeIncestPornXXXSex_**    | video · all ✦                  | None                           |
| `rl`   | **_RapeLust_**                | video · search ✦ · tag ✦ · star ✦ | actors · code · date · description · tags |
| `sb`   | **_SpankBang_**               | video · model ✦ · search ✦ · tag ✦ | actors · description · tags    |
| `tna`  | **_TNAflix_**                 | video · search ✦               | actors · date · description · studios · tags |
| `tr`   | **_TopRealIncestVideos_**     | video · search                 | None                           |
| `tt`   | **_TabooTube_** †             | video · search                 | actors · date · description · studios · tags |
| `tx`   | **_TXXX_** †                  | video · search                 | actors · description · studios · tags |
| `xh`   | **_xHamster_** †              | video · model ✦ · studio ✦ · search ✦ · tag ✦ | actors · studios · tags        |
| `xn`   | **_XNXX_** †                  | video · search ✦ · model ✦ · tag ✦ · studio ✦ | actors · date · description · studios · tags |
| `xr`   | **_Xrares_**                  | video · search ✦               | description · tags             |
| `xv`   | **_XVideos_** †               | video · search ✦ · studio ✦ · model ✦ · tag ✦ · playlist · profile | actors · studios · tags        |

✦ _Supports pagination; see optional arguments below._

† _Selenium required._

‡ _Combine terms with "&"._

---

### Command-Line Arguments [ > ]

#### CLI Mode (default)
```bash
scrape [args] [optional arguments]
```

| argument             | summary                                                                                              |
| ---------------------| ---------------------------------------------------------------------------------------------------- |
| `-p {p}.{video}`     | start scraping on a given page and video (e.g., `-p 12.9` to start at video 9 on page 12.            |
| `-o, --overwrite`    | download all videos, ignoring `.state` and overwriting existing media when filenames collide. ⚠      |
| `-n, --re_nfo`       | refresh metadata and write new `.nfo` files, irrespective of whether `--overwrite` is set. ⚠         |
| `-a, --applystate`   | retroactively add URL to `.state` without re-downloading if local file matches (`-o` has priority).  |
| `-t, --table {site}` | output site table in Markdown format and exit (specify site code or leave empty for all sites).     |
| `-d, --debug`        | enable detailed debug logging.                                                                       |
| `-h, --help`         | show the help submenu.                                                                               |

#### Server Mode
```bash
scrape --server [server options]
```

| argument             | summary                                                                                              |
| ---------------------| ---------------------------------------------------------------------------------------------------- |
| `--server`           | run as FastAPI server instead of CLI mode.                                                          |
| `--host {host}`      | host to bind the API server to (overrides config.yaml).                                             |
| `--port {port}`      | port to bind the API server to (overrides config.yaml).                                             |
| `-d, --debug`        | enable detailed debug logging.                                                                       |
| `-h, --help`         | show server-specific help menu.                                                                      |

**⚠ Caution**: Using `--overwrite` or `--re_nfo` risks overwriting different videos or `.nfo` files with identical names—a growing concern as your collection expands and generic titles (e.g., "Hot Scene") collide. Mitigate this by adding `name_suffix: "{unique site identifier}"` in a site's YAML config (e.g., `name_suffix: " - Motherless.com"` for Motherless, where duplicate titles are rampant).

---

### Usage Examples 🙋

1. **_All videos on Massy Sweet's 'pornstar' page on PornHub that aren't saved locally, refreshing metadata for already saved videos we encounter again:_**
     ```bash
     scrape ph pornstar "Massy Sweet" -n
     ```

2. **_All videos produced by MissaX from FamilyPornHD, overwriting existing copies:_**
     ```bash
     scrape fphd studio "MissaX" -o
     ```

3. **_Chloe Temple's videos involving brother-sister (BS) relations not yet saved locally, starting on page 4 of results with 6th video, recording URL for faster scraping when upon matching with local file:_**
     ```bash
     scrape if tag "Chloe Temple & BS" -a -p 4.6
     ```

4. **_Down and dirty in debug logs for scraping that "real" incest stuff on Lonefun:_**
     ```bash
     scrape lf tag "real incest" -d
     ```

5. **_One particular vintage mother/daughter/son video on Motherless:_**
     ```bash
     scrape https://motherless.com/2ABC9F3
     ```

6. **_All videos from Halle Von's pornstar page on XNXX:_**
     ```bash
     scrape https://www.xnxx.com/pornstar/halle-von
     ```

---

### API Server Mode 🌐

**_Smutscrape_** can now run as a FastAPI server, allowing you to execute scraping commands via HTTP requests. This is useful for integrating smutscrape into other applications or creating web interfaces.

```bash
# Start the API server (uses config.yaml settings or defaults to 127.0.0.1:6999)
python scrape.py --server

# Override with command-line arguments
python scrape.py --server --host 0.0.0.0 --port 8080
```

Configure default server settings in `config.yaml`:
```yaml
api_server:
  host: "127.0.0.1"
  port: 6999
```

**Available endpoints:**
- `GET /` - API information
- `GET /sites` - List all supported sites
- `GET /sites/{code}` - Get site details
- `POST /scrape` - Execute a scrape command

**Example API usage:**
```bash
# Execute a scrape command via API
curl -X POST http://localhost:6999/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "command": "xh search \"Vintage taboo\"",
    "re_nfo": true
  }'
```

See [API.md](API.md) for complete API documentation.

---

## Advanced Configuration ⚙️

### Download Destinations 📁

Define destinations in `config.yaml`. The first is primary, any others are fallbacks.

```yaml
download_destinations:
  - type: smb
    server: "192.168.69.69"
    share: "media"
    path: "xxx"
    username: "perv"
    password: "th3P3rv3rtsGu1d3"
    permissions:
      uid: 1000
      gid: 3003
      mode: "750"
    temporary_storage: "/Users/perv/.private/incomplete"
  - type: local
    path: "/Users/perv/.private/xxx"
```

*Smutscrape was built with SMB in mind, and it's the recommended mode when it fits.*

### Filtering Content 🚫

Add any content you want Smutscrape to avoid altogether to the `ignored` terms list in your `config.yaml`:

```yaml
ignored:
  - "JOI"
  - "Age Play"
  - "Psycho Thrillers"
  - "Virtual Sex"
```

All metadata fields are checked against the `ignored` list, so you can include specific genres, sex acts, performers, studios, etc. that you do not want content of.

### Selenium & Chromedriver 🕵️‍♂️

For Javascript-heavy sites (marked on the table with †), **selenium** with **chromedriver** is required. By default, the script uses `webdriver-manager` for seamless setup. Some setups require a manual installation, including macOS typically. This worked for me:

1. **Install Chrome Binary**:

  ```bash
  wget https://storage.googleapis.com/chrome-for-testing-public/134.0.6998.88/mac-arm64/chrome-mac-arm64.zip
  unzip chrome-mac-arm64.zip
  chmod +x "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
  sudo mv "chrome-mac-arm64/Google Chrome for Testing.app" /Applications/
  ```

2. **Install Chromedriver**:

  ```bash
  wget https://storage.googleapis.com/chrome-for-testing-public/134.0.6998.88/mac-arm64/chromedriver-mac-arm64.zip
  unzip chromedriver-mac-arm64.zip
  chmod +x chromedriver-mac-arm64/chromedriver
  sudo mv chromedriver-mac-arm64/chromedriver /usr/local/bin/chromedriver
  ```

3. **Update `config.yaml`**:

  ```yaml
  selenium:
    mode: "local"
    chromedriver_path: "/usr/local/bin/chromedriver"
    chrome_binary: "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
  ```

### VPN Support 🔒

**_Smutscrape_** can be set to automatically rotate VPN exit-nodes, using most existing VPN apps that have CLI tools. In `config.yaml`, enable and configure:

```yaml
vpn:
  enabled: true
  vpn_bin: "/usr/bin/protonvpn"
  start_cmd: "{vpn_bin} connect -f"
  new_node_cmd: "{vpn_bin} connect -r"
  new_node_time: 1200  # Refresh IP every 20 minutes
```

---

## Contributing 🤝

**_Smutscrape_** welcomes contributions! The application features a modular, PyPI-ready package structure that makes collaboration straightforward. Adding site configurations—YAML files with URL schemes and CSS selectors—is a simple, valuable contribution.

Inspired by [Stash CommunityScrapers](https://github.com/stashapp/CommunityScrapers), **_Smutscrape_**'s YAML configs adapt its structure. We use CSS selectors instead of XPath (though conversion is straightforward), and metadata fields port easily. The challenge is video downloading—some sites use iframes or countermeasures—but the yt-dlp fallback often simplifies this. Adapting a CommunityScrapers site for **_Smutscrape_** is a great way to contribute. Pick a site, tweak the config, and submit a pull request!

---

Scrape responsibly! You're on your own. 🧠💭
