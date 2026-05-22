# Third-Party Licenses

Agent-OS uses the following open-source libraries and code:

---

## Scrapling — Adaptive Scraping Engine

- **Source:** https://github.com/D4Vinci/Scrapling
- **Author:** Karim Shoair
- **License:** BSD 3-Clause License
- **Copyright:** Copyright (c) 2024, Karim Shoair
- **Used in:** `src/tools/adaptive_scraper.py`, `src/tools/proxy_rotator.py`
- **Components:** Adaptive element relocation algorithm, proxy rotation engine

### License Text

```
BSD 3-Clause License

Copyright (c) 2024, Karim Shoair

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

---

## agent-browser — DOM Snapshot / Token Saving

- **Source:** https://github.com/vercel-labs/agent-browser
- **Author:** Vercel Labs
- **License:** Apache-2.0
- **Used in:** `src/tools/dom_snapshot.py`
- **Components:** Accessibility tree snapshot, compact rendering, ref-based element identification, cursor-interactive detection, StaticText aggregation

---

## Other Dependencies

See `requirements.txt` for full dependency list.
