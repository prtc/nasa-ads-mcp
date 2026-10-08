# NASA ADS in Claude: a guide for students

*[Leia em português](guia-do-estudante.md)*

This guide sets you up to search the NASA Astrophysics Data System (ADS) from Claude: find papers, read abstracts, check citations, export BibTeX, and use your ADS libraries, all from a conversation. It takes about 15 minutes, once.

If you are in the **Pleiad Astronomy** group, some steps are already done for you; they're marked 🌟.

## What you need

- A Claude account on a paid plan. 🌟 Pleiad members: use your Pleiad Astronomy account.
- A free NASA ADS account: [create one here](https://ui.adsabs.harvard.edu/user/account/register) if you don't have one.
- About 15 minutes and a terminal (on Windows, PowerShell).

## Step 1: Get your ADS token

The token is how ADS knows the requests come from you. **Treat it like a password**: don't share it, paste it in a chat, or commit it to a repository.

1. Log in at [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu).
2. Open [Account → Settings → API Token](https://ui.adsabs.harvard.edu/user/settings/token).
3. Generate a token (or use the one shown there) and copy it. You'll paste it in Step 5.

## Step 2: Install uv

uv is a small tool that installs the server's Python packages (and Python itself, if needed).

- **Linux and macOS:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows (PowerShell):**
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

Then **open a new terminal** and check with `uv --version`.

## Step 3: Install Claude Code and log in

- **Linux, macOS, WSL:**
  ```bash
  curl -fsSL https://claude.ai/install.sh | bash
  ```
- **Windows (PowerShell):**
  ```powershell
  irm https://claude.ai/install.ps1 | iex
  ```

Open a new terminal, run `claude`, and log in through the browser. 🌟 Pleiad members: choose the Pleiad Astronomy organization.

Prefer an app to the terminal? See [Claude Desktop](#using-claude-desktop-instead) below.

## Step 4: Get the plugin

🌟 **Pleiad members:** it's already installed for you. The first time you start Claude Code, it downloads in the background. When you see `Plugins changed. Run /reload-plugins to activate.`, run `/reload-plugins` (or just restart Claude Code).

**Everyone else:** in your terminal, run:
```bash
claude plugin marketplace add prtc/nasa-ads-mcp
claude plugin install nasa-ads@nasa-ads-mcp
```

## Step 5: Give the plugin your token

Use **either** option.

**Option A: the plugin's settings (stored in your system's secure credential store).** If Claude Code asks for the "NASA ADS API token", paste it. If it didn't ask, run `/plugin` inside Claude Code, open the **Installed** tab, choose **NASA ADS**, and configure it there.

**Option B: a file (always works, also used by the `ads` Python package).** On Linux or macOS:
```bash
mkdir -p ~/.ads
nano ~/.ads/dev_key
```
Paste the token, then save and exit (Ctrl+O, Enter, Ctrl+X). Then make the file private:
```bash
chmod 600 ~/.ads/dev_key
```

## Step 6: Check that it works

Start a new Claude Code session and run `/mcp`. You should see `plugin:nasa-ads:nasa-ads` marked as connected. The first start takes a few extra seconds while uv installs things.

Then just ask, for example:

- *Find the 10 most cited refereed papers on stellar population synthesis since 2015 and summarize their approaches.*
- *Show me the abstract of 2005A&A...443..735C.*
- *Export BibTeX for these papers into refs.bib: …*
- *What's in my ADS library "Thesis references"?*

Claude asks your permission the first time it uses each tool.

**Search tips.** Claude understands plain language, but ADS search syntax gives you precision, and you can use it directly. Remember that ADS requires *every* word to match: a pasted full title with one word written differently ("microns" for "μm") finds nothing, so a few distinctive words work better.

| You write | It finds |
| :-- | :-- |
| `first_author:"Coelho, P."` | papers with that first author |
| `year:2020-2025` | a range of years |
| `property:refereed` | refereed papers only |
| `abs:"stellar populations"` | the phrase in title, abstract, or keywords |
| `title:(synthetic stellar spectra)` | these words in the title, in any order |
| `pos(author:"Coelho, P", 2)` | papers with that second author (`1, 3` for first to third) |
| `citations(bibcode:2005A&A...443..735C)` | papers that cite that paper |
| `references(bibcode:2005A&A...443..735C)` | papers that paper cites |

## Using it well

The tools fetch real records from ADS, but Claude writes the summaries, and summaries can be wrong.

- **Check before you cite.** Open the ADS page of any paper you plan to cite, and read at least the abstract yourself.
- **Get BibTeX from the tool,** never typed by Claude from memory. The `export_bibtex` tool returns exactly what ADS exports.
- **Author metrics match names, not people.** A common name can pull in other people's papers. The author tools search the astronomy collection by default and say so in every result; give your ORCID iD to count only your own papers. For a CV, ask for refereed papers only, or papers with at most, say, 20 authors, so large collaboration papers don't dominate.
- **Libraries are your real ADS libraries.** Creating one or adding papers changes your ADS account. Claude asks before it does.
- **Your token is yours.** Everything the tools do happens under your ADS account and counts against your daily ADS limit.

## Using Claude Desktop instead

On macOS, Windows, or Linux (the Linux app is in beta), you can use the server in Claude Desktop's chat:

1. Download [`nasa-ads.mcpb`](https://github.com/prtc/nasa-ads-mcp/releases/latest/download/nasa-ads.mcpb).
2. Double-click it (or drag it into Claude Desktop, or go to **Settings → Extensions → Advanced settings → Install Extension…**).
3. Paste your ADS token when asked.

If Claude Desktop says it can't find `uv`, do Step 2 and restart Claude Desktop.

## Troubleshooting

| You see | What to do |
| :-- | :-- |
| "No ADS API token found" | Do Step 5, then start a new session |
| "ADS rejected the API token (401)" | The token is wrong or was regenerated: copy it again from ADS (Step 1) and redo Step 5 |
| "ADS rate limit reached" | ADS limits requests per day; wait until the time given, or ask for fewer results |
| `uv: command not found` | Open a new terminal after installing uv, or redo Step 2 |
| The tools appear twice | You also set the server up by hand earlier: run `claude mcp remove nasa-ads` |
| `plugin:nasa-ads:nasa-ads` is not connected | Run `claude --debug` and look for lines mentioning nasa-ads, then ask for help |

**Still stuck?** Pleiad members: ask Paula. Everyone: open an issue at [github.com/prtc/nasa-ads-mcp/issues](https://github.com/prtc/nasa-ads-mcp/issues).
