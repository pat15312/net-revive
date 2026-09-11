# Optional browser regression check

These checks use the real application with an in-memory fake UniFi adapter and a disposable SQLite database. They never connect to a controller. The server must be fresh for each run because the suite completes first-run setup.

From the repository root, with the Python development environment activated:

```bash
python tests/browser/server.py
```

In another terminal, install the browser test tool outside the application and run the suite:

```bash
npm install --prefix /tmp/netrevive-browser-tools playwright@1.58.2
/tmp/netrevive-browser-tools/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/netrevive-browser-tools/node_modules node tests/browser/check.cjs
```

Chromium may need its usual system libraries (`playwright install --with-deps chromium` on a supported Linux test host). Node and Chromium are development tools; they are not needed in the production container. Screenshots are written to ignored `test-results/`. The script checks setup, Admin settings, discovery, group/user creation, short-hold cancellation, keyboard restart, persistent lockout, remembered user, history, mobile overflow, external requests and JavaScript errors.
