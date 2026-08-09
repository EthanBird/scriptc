from pathlib import Path
import os, shutil, subprocess

SOURCE = Path('packages/compiler/src/frontend/lowering/lower-stmts.ts')
OUT = Path('PRIME_OBJECT_ENTRIES_RUNNER_PROBE.txt')
LOG: list[str] = []


def replace_once(old: str, new: str) -> None:
    text = SOURCE.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'expected one probe anchor, found {count}')
    SOURCE.write_text(text.replace(old, new, 1), encoding='utf-8')


def run(args: list[str], cwd: str | None = None, env: dict[str, str] | None = None, timeout: int = 1800):
    cp = subprocess.run(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    return cp.returncode, cp.stdout or ''


try:
    replace_once(
        '''        const mapped = L.mapTypeOf(L.typeOf(arg));
        const probed = mapped?.kind === "record" ? null : probeLower(L, arg);
        const recT = mapped?.kind === "record" ? mapped : probed?.type.kind === "record" ? probed.type : null;
        if (recT) {''',
        '''        const argTsType = L.typeOf(arg);
        const mapped = L.mapTypeOf(argTsType);
        const probed = mapped?.kind === "record" ? null : probeLower(L, arg);
        const recT = mapped?.kind === "record" ? mapped : probed?.type.kind === "record" ? probed.type : null;
        const probeFile = arg.getSourceFile().fileName;
        if (probeFile.includes("/core/extensions/runner.ts") || probeFile.includes("/interactive/theme/theme.ts")) {
          const indexInfos = L.checker.getIndexInfosOfType(argTsType);
          const indexText = indexInfos.map((info) =>
            `${L.checker.typeToString(info.keyType)}=>${L.checker.typeToString(info.type)}`,
          ).join(" || ");
          const sym = argTsType.getAliasSymbol?.() ?? argTsType.getSymbol?.();
          const declText = sym
            ? L.checker.declarationsOf(sym).map((d) => `${d.kind}@${d.getSourceFile().fileName}`).join(" || ")
            : "none";
          console.error(
            `[SCRIPTC_ENTRIES_SHALLOW_PROBE] file=${probeFile} text=${arg.getText()} ts=${L.checker.typeToString(argTsType)} flags=${argTsType.flags} indexes=${indexText || "none"} symbol=${sym?.name ?? "none"} decls=${declText} mapped=${mapped ? L.fmt(mapped) : "null"} probed=${probed ? L.fmt(probed.type) : "null"}`,
          );
        }
        if (recT) {''',
    )

    version = Path('.node-version').read_text(encoding='utf-8').strip()
    node_dir = Path(f'/tmp/node-v{version}-linux-x64')
    env = os.environ.copy()
    if not (node_dir / 'bin/node').exists():
        archive = Path(f'/tmp/node-v{version}-linux-x64.tar.xz')
        code, text = run(['curl', '-fsSL', f'https://nodejs.org/dist/v{version}/node-v{version}-linux-x64.tar.xz', '-o', str(archive)])
        if code: raise RuntimeError(text)
        code, text = run(['tar', '-xJf', str(archive), '-C', '/tmp'])
        if code: raise RuntimeError(text)
    env['PATH'] = f"{node_dir / 'bin'}:{env.get('PATH', '')}"
    for cmd in [
        ['corepack', 'enable'],
        ['corepack', 'prepare', 'pnpm@11.1.3', '--activate'],
        ['pnpm', 'install', '--frozen-lockfile'],
        ['pnpm', 'build'],
    ]:
        code, text = run(cmd, env=env)
        if code: raise RuntimeError(f"{' '.join(cmd)} failed\n{text[-8000:]}")

    prime = '/tmp/scriptc-prime-entries-shallow-probe'
    shutil.rmtree(prime, ignore_errors=True)
    code, text = run(['git', 'clone', '--depth', '1', 'https://github.com/EthanBird/prime-agent.git', prime], env=env)
    if code: raise RuntimeError(f'prime clone failed\n{text[-8000:]}')
    code, text = run(['npm', 'ci'], cwd=prime, env=env)
    if code: raise RuntimeError(f'prime npm ci failed\n{text[-8000:]}')
    code, text = run(['npm', 'run', 'build'], cwd=prime, env=env)
    if code: raise RuntimeError(f'prime baseline build failed\n{text[-8000:]}')

    cli = str((Path.cwd() / 'packages/cli/dist/main.js').resolve())
    code, text = run(['node', cli, 'build', 'packages/coding-agent/src/cli-main.ts', '--dynamic', '-o', '/tmp/prime-entries-shallow-probe-bin'], cwd=prime, env=env)
    probe = [line for line in text.splitlines() if 'SCRIPTC_ENTRIES_SHALLOW_PROBE' in line]
    relevant = [line for line in text.splitlines() if 'runner.ts:84' in line or 'theme.ts:358' in line or 'Object.entries' in line]
    LOG.append(f'prime-scriptc-exit={code}')
    LOG.append('=== shallow probe lines ===')
    LOG.extend(probe)
    LOG.append('=== Object.entries diagnostics ===')
    LOG.extend(relevant[-100:])
    if not probe:
        LOG.append('NO SHALLOW PROBE LINES EMITTED')
except Exception as exc:
    LOG.append(f'PROBE FAILURE: {type(exc).__name__}: {exc}')
finally:
    subprocess.run(['git', 'checkout', '--', str(SOURCE)], check=False)
    OUT.write_text('\n'.join(LOG) + '\n', encoding='utf-8')
