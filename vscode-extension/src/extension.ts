import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { execFile } from 'child_process';

// --- Profile reading ---

function getAuthMode(): string {
  try {
    const authPath = path.join(os.homedir(), '.codex', 'auth.json');
    const content = fs.readFileSync(authPath, 'utf-8');
    const data = JSON.parse(content);
    return data.auth_mode ?? 'unknown';
  } catch {
    return 'unknown';
  }
}

function getProviderFromConfig(): string {
  try {
    const configPath = path.join(os.homedir(), '.codex', 'config.toml');
    const lines = fs.readFileSync(configPath, 'utf-8').split('\n');
    for (const line of lines) {
      const m = line.match(/^\s*model_provider\s*=\s*"([^"]+)"/);
      if (m) return m[1];
    }
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

function getCurrentProfile(): string {
  try {
    const authMode = getAuthMode();
    if (authMode === 'chatgpt') {
      return 'chatgpt';
    }
    return getProviderFromConfig();
  } catch {
    return 'unknown';
  }
}

function listProfiles(): string[] {
  try {
    const profilesDir = path.join(os.homedir(), '.codex', 'profiles');
    const entries = fs.readdirSync(profilesDir, { withFileTypes: true });
    return entries
      .filter(e => e.isDirectory())
      .map(e => e.name)
      .sort();
  } catch {
    return [];
  }
}

// --- Status bar ---

let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;

async function getTodayTokens(ctxPath: string): Promise<string> {
  return new Promise((resolve) => {
    execFile(ctxPath, ['stats'], { timeout: 3000 }, (error, stdout) => {
      if (error) { resolve(''); return; }
      // Parse line like "Tokens   (today): 25,731,981"
      const match = stdout.match(/Tokens\s+\(today\):\s+([\d,]+)/);
      if (!match) { resolve(''); return; }
      const n = parseInt(match[1].replace(/,/g, ''), 10);
      if (n >= 1_000_000) resolve(` ${(n / 1_000_000).toFixed(1)}M`);
      else if (n >= 1_000) resolve(` ${Math.round(n / 1_000)}K`);
      else if (n > 0) resolve(` ${n}`);
      else resolve('');
    });
  });
}

async function updateStatusBar(): Promise<void> {
  const profile = getCurrentProfile();
  let ctxPath: string | undefined;
  try {
    ctxPath = await findCtxPath();
  } catch {
    ctxPath = undefined;
  }
  let tokenSuffix = '';
  if (ctxPath) {
    tokenSuffix = await getTodayTokens(ctxPath);
  }
  if (profile === 'unknown') {
    statusBarItem.text = '$(circuit-board) ctx: ?';
    statusBarItem.tooltip = 'ctx-keeper: cannot read current profile';
  } else {
    statusBarItem.text = `$(circuit-board) ${profile}${tokenSuffix}`;
    statusBarItem.tooltip = `ctx-keeper: ${profile}${tokenSuffix ? ` | today: ${tokenSuffix.trim()}` : ''}\nClick to switch profile`;
  }
  statusBarItem.show();
}

// --- Switch command ---

function findCtxPath(): Promise<string> {
  return new Promise((resolve, reject) => {
    // Try common known paths first
    const commonPaths = [
      '/opt/homebrew/bin/ctx',
      '/usr/local/bin/ctx',
      path.join(os.homedir(), '.local', 'bin', 'ctx'),
    ];

    for (const p of commonPaths) {
      if (fs.existsSync(p)) {
        resolve(p);
        return;
      }
    }

    // Fall back to `which ctx`
    execFile('which', ['ctx'], (error, stdout) => {
      if (error || !stdout.trim()) {
        reject(new Error('ctx not found. Install ctx-keeper and ensure ctx is on your PATH.'));
      } else {
        resolve(stdout.trim());
      }
    });
  });
}

async function switchProfile(): Promise<void> {
  const profiles = listProfiles();
  const current = getCurrentProfile();

  if (profiles.length === 0) {
    vscode.window.showWarningMessage(
      'ctx-keeper: No profiles found under ~/.codex/profiles/'
    );
    return;
  }

  interface ProfileItem extends vscode.QuickPickItem {
    profile: string;
  }

  const items: ProfileItem[] = profiles.map(p => ({
    label: p === current ? `→ ${p}` : `  ${p}`,
    description: p === current ? '(current)' : '',
    profile: p,
  }));

  const selected = await vscode.window.showQuickPick(items, {
    placeHolder: 'Select a Codex profile to switch to',
  });

  if (!selected) {
    return;
  }

  if (selected.profile === current) {
    vscode.window.showInformationMessage(`Already on profile: ${current}`);
    return;
  }

  let ctxPath: string;
  try {
    ctxPath = await findCtxPath();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    vscode.window.showErrorMessage(
      `ctx-keeper: ${msg}\nInstall with: pip install ctx-keeper`
    );
    return;
  }

  execFile(ctxPath, ['switch', selected.profile], (error, _stdout, stderr) => {
    if (error) {
      vscode.window.showErrorMessage(
        `ctx switch failed: ${stderr || error.message}`
      );
    } else {
      vscode.window.showInformationMessage(`Switched to ${selected.profile}`);
      updateStatusBar();
    }
  });
}

// --- Stats command ---

async function showStats(): Promise<void> {
  let ctxPath: string;
  try {
    ctxPath = await findCtxPath();
  } catch {
    vscode.window.showErrorMessage('ctx-keeper not found. Install with: pip install ctx-keeper');
    return;
  }
  outputChannel.clear();
  outputChannel.show(true);
  outputChannel.appendLine('Loading stats...');

  execFile(ctxPath, ['stats', '--week'], (error, stdout, stderr) => {
    outputChannel.clear();
    if (error) {
      outputChannel.appendLine(`Error: ${stderr || error.message}`);
    } else {
      outputChannel.appendLine(stdout);
    }
  });
}

// --- File watcher ---

let watcher: fs.FSWatcher | undefined;
let pollTimer: ReturnType<typeof setInterval> | undefined;

function startWatcher(): void {
  const authPath = path.join(os.homedir(), '.codex', 'auth.json');

  try {
    watcher = fs.watch(authPath, () => {
      updateStatusBar();
    });

    watcher.on('error', () => {
      // Ignore errors — file may not exist yet
    });
  } catch {
    // File doesn't exist yet; watcher not started
  }

  // 5-second poll as fallback (covers cases where fs.watch fires late on macOS)
  pollTimer = setInterval(() => {
    updateStatusBar();
  }, 5000);
}

function stopWatcher(): void {
  if (watcher) {
    watcher.close();
    watcher = undefined;
  }
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = undefined;
  }
}

// --- Activate / Deactivate ---

export function activate(context: vscode.ExtensionContext): void {
  // 1. Create status bar item (left side, priority 100)
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    100
  );

  // 2. Set command to ctx-keeper.switchProfile
  statusBarItem.command = 'ctx-keeper.switchProfile';

  // 3. Register the switchProfile command
  const disposableCommand = vscode.commands.registerCommand(
    'ctx-keeper.switchProfile',
    switchProfile
  );

  // 4. Create output channel and register showStats command
  outputChannel = vscode.window.createOutputChannel('ctx-keeper');
  context.subscriptions.push(outputChannel);

  const statsCmd = vscode.commands.registerCommand('ctx-keeper.showStats', showStats);
  context.subscriptions.push(statsCmd);

  // 5. Call updateStatusBar()
  updateStatusBar();

  // 6. Start file watcher
  startWatcher();

  // 7. Push disposables to context.subscriptions
  context.subscriptions.push(statusBarItem, disposableCommand);
}

export function deactivate(): void {
  stopWatcher();
}
