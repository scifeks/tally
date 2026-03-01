# Phase 4 Testing Protocol

End-to-end validation of the nmap scan → RAG ingestion → semantic search/chat pipeline.

---

## Prerequisites

Before running any tests, verify the following are in place:

- [ ] **Ollama installed and running**
  ```
  ollama serve
  ```
  Verify: `curl http://localhost:11434/api/tags` returns JSON.

- [ ] **LLM model pulled**
  ```
  ollama pull qwen2.5:7b
  ```

- [ ] **Embedding model pulled**
  ```
  ollama pull nomic-embed-text
  ```

- [ ] **nmap installed**
  ```
  which nmap
  ```
  Install if missing: `apt install nmap`

- [ ] **Python dependencies installed**
  ```
  pip install -r requirements.txt
  ```

- [ ] **tally launches without errors**
  ```
  python main.py
  ```

---

## Scenario 1: Project Creation

**Goal:** Confirm project directory structure is created correctly.

Steps:
1. Launch tally: `python main.py`
2. Run `new-project`
3. Enter project name: `test-phase4`
4. Skip adding repositories (answer `N`)
5. Confirm the prompt switches to `[test-phase4]>`

Expected file structure under `projects/test-phase4/`:
```
config/
  project.json
  repositories.json
  nmap_hosts.json   (empty: {})
  endpoints/
chroma_db/
tool_outputs/
  nmap/
  semgrep/
  osv-scanner/
  gitleaks/
  zap/
sessions/
```

Pass criteria:
- [ ] All directories exist
- [ ] `config/project.json` contains correct project name and `created` timestamp
- [ ] `config/nmap_hosts.json` contains `{}`
- [ ] REPL prompt shows `[test-phase4]>`

---

## Scenario 2: Nmap Configuration

**Goal:** Verify nmap profile config is read correctly.

Steps:
1. Manually write nmap profile to `projects/test-phase4/config/nmap_hosts.json`:
   ```json
   {
     "localhost": {
       "hosts": ["127.0.0.1"],
       "nmap_args": "-p 22,80,443 -sV"
     }
   }
   ```
2. Restart tally and switch to `test-phase4` project.
3. Confirm no errors on startup.

Pass criteria:
- [ ] File written successfully
- [ ] No JSON parse errors when tally loads the project

---

## Scenario 3: Scan Execution

**Goal:** Verify `scan -t nmap localhost` runs nmap and saves output.

Steps:
1. In the REPL: `scan -t nmap localhost`
2. At the approval prompt, review the command shown and type `y`
3. Wait for scan to complete

Pass criteria:
- [ ] Command displayed correctly before approval (e.g. `nmap -p 22,80,443 -sV -oX - 127.0.0.1`)
- [ ] Scan completes with `✓ Scan complete:`
- [ ] Summary shows `N hosts up, M open ports`
- [ ] Output file created in `projects/test-phase4/tool_outputs/nmap/`
- [ ] Output file path printed in REPL
- [ ] File is valid XML (open in text editor, confirm `<?xml` header)

---

## Scenario 4: Ingestion

**Goal:** Verify findings are stored in ChromaDB.

Steps:
1. After the scan completes, at the `Ingest findings? [y/N]:` prompt, type `y`
2. Confirm ingestion count message appears
3. Run `stats`

Pass criteria:
- [ ] `✓ Ingested N findings` shown (N > 0)
- [ ] `stats` shows non-zero `Total Documents`
- [ ] `stats` shows `nmap` under by-tool counts
- [ ] `Last Updated` timestamp shown

---

## Scenario 5: Search

**Goal:** Verify semantic search returns relevant results.

Steps:
1. Run `search port 22`
2. Run `search 127.0.0.1`
3. Run `search thisdoesnotexistxyz`

Pass criteria:
- [ ] `search port 22` returns results with `finding_type` = `open_port` (if port 22 is open)
- [ ] `search 127.0.0.1` returns host or port results referencing `127.0.0.1`
- [ ] `search thisdoesnotexistxyz` returns `No results found.` (graceful empty case)
- [ ] Results table shows Finding/Tool/Type/Relevance columns
- [ ] Relevance scores are decimal numbers (lower = more relevant)

---

## Scenario 6: Chat

**Goal:** Verify RAG-augmented chat uses scan context.

Steps:
1. Run `chat what ports are open on localhost?`
2. Run `chat summarize the scan findings`
3. Run `chat are there any security concerns?`

Pass criteria:
- [ ] Response rendered in a cyan Panel titled `Assistant`
- [ ] Response references actual IP addresses or port numbers from the scan
- [ ] Response is coherent English text (not an error message)
- [ ] No Python traceback printed
- [ ] `chat` command with no message shows usage error

---

## Scenario 7: Re-scan and Upsert

**Goal:** Verify that re-running a scan does not produce duplicate documents.

Steps:
1. Note the `Total Documents` count from `stats`
2. Run `scan -t nmap localhost` again, approve, ingest
3. Run `stats` again

Pass criteria:
- [ ] Document count is **the same** before and after the second ingest
- [ ] `search 127.0.0.1` still returns the same number of results
- [ ] No error messages during second ingest

---

## Scenario 8: Project Isolation

**Goal:** Verify that each project's ChromaDB collection is independent.

Steps:
1. Create a second project: `new-project`, name it `test-phase4-b`
2. Run `stats` — should show `No data ingested yet`
3. Run `search localhost` — should show `No results found`
4. Switch back: `switch test-phase4`
5. Run `stats` — should show the original document count

Pass criteria:
- [ ] `test-phase4-b` starts with zero documents
- [ ] Searching in `test-phase4-b` returns no results
- [ ] Switching back to `test-phase4` restores previous results
- [ ] No data leakage between projects

---

## Scenario 9: Error Handling

**Goal:** Verify edge cases are handled gracefully.

Steps:
1. Stop Ollama (`pkill ollama`), then run `stats`
2. Run `search` with no query
3. Run `chat` with no message
4. Run `scan -t nmap nonexistent-profile`
5. Restart Ollama and verify everything recovers

Pass criteria:
- [ ] Ollama down: clear error message, no Python traceback
- [ ] `search` with no args: `Usage: search <query>`
- [ ] `chat` with no args: `Usage: chat <message>`
- [ ] Unknown profile: error message listing available profiles
- [ ] After restarting Ollama: all commands work again

---

## Known Limitations

- `stats` requires Ollama to be running (RAGEngine initialises the embedding function on startup). This is a known architectural limitation — refactoring to lazy-init embeddings is deferred.
- Very large nmap scans (e.g. scanning `/24` subnets) may take several minutes. Use `--timeout` if needed: `scan -t nmap localhost --timeout 600`
- ChromaDB distance scores near `1.0` indicate low relevance; scores near `0.0` indicate high relevance.

---

## Running Automated Tests

```bash
# From the tally project root
pytest tests/validation/ -v

# Skip slow tests (nmap scan)
pytest tests/validation/ -v -m "not slow"

# Run only unit tests (no Ollama or nmap required)
pytest tests/validation/ -v -m "not requires_ollama and not requires_nmap"
```
