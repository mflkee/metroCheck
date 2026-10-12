#!/usr/bin/env node
/**
 * The fleet UI guard.
 *
 * Two rules that the four metro* frontends agreed on, both of which are easy to break
 * by accident and invisible in review:
 *
 *  1. A vendored registry file is never edited in place. The look belongs to
 *     `mflkee/metro-ui`; a change goes there and the service re-adds the item
 *     (`npx shadcn@latest add @metro/<item> --overwrite`). This script keeps a hash of
 *     every vendored file (`fleet-ui.manifest.json`) and fails when one drifts.
 *  2. A colour is a token, never a literal. A hex value or a Tailwind palette utility
 *     (`text-emerald-400`, `bg-[#edf2f5]`) cannot follow the theme, and the fleet has
 *     seven themes.
 *
 * Usage:
 *   node scripts/fleet-ui.mjs check      # verify (runs in the build)
 *   node scripts/fleet-ui.mjs manifest   # re-hash the vendored files after an add
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifestPath = path.join(root, "fleet-ui.manifest.json");

/** Everything `npx shadcn@latest add @metro/...` writes into a service. */
const VENDORED = [
  "src/metro-theme.css",
  "src/lib/theme-store.ts",
  "src/lib/utils.ts",
  "src/lib/mentions.ts",
  "src/lib/numericInput.ts",
  "src/components/app-shell.tsx",
  "src/components/theme-switcher.tsx",
  "src/components/version-badge.tsx",
  "src/components/date-input.tsx",
  "src/components/time-input.tsx",
  "src/components/number-input.tsx",
  "src/components/mention-text.tsx",
  "src/components/floating-autocomplete-menu.tsx",
  "src/components/icon-action-button.tsx",
  "src/components/ui",
];

const SCAN_EXTENSIONS = new Set([".ts", ".tsx", ".css"]);

/** The Tailwind palette: a colour that is not a token. */
const PALETTE =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const PALETTE_UTILITY = new RegExp(
  `\\b(?:text|bg|border|ring|divide|from|to|via|fill|stroke|outline|shadow|decoration|accent|caret)-\\[?(?:${PALETTE})-\\d{2,3}`,
);
const HEX_COLOUR = /#[0-9a-fA-F]{3,8}\b/;

/** `#rrggbb` is fine in these places (the theme itself, tests, comments about them). */
const HEX_ALLOWED_IN = [/\.test\.[jt]sx?$/, /src[\\/]metro-theme\.css$/];

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) {
      continue;
    }
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      walk(full, out);
    } else if (SCAN_EXTENSIONS.has(path.extname(entry))) {
      out.push(full);
    }
  }
  return out;
}

function vendoredFiles() {
  const files = [];
  for (const entry of VENDORED) {
    const full = path.join(root, entry);
    if (!existsSync(full)) {
      continue;
    }
    if (statSync(full).isDirectory()) {
      walk(full, files);
    } else {
      files.push(full);
    }
  }
  return files.sort();
}

const relative = (file) => path.relative(root, file).split(path.sep).join("/");
const hash = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");

function writeManifest() {
  const files = {};
  for (const file of vendoredFiles()) {
    files[relative(file)] = hash(file);
  }
  const manifest = {
    $comment:
      "Hashes of the files vendored from the metro-ui registry. Regenerate with `npm run check:ui -- manifest` right after adding or updating an item; never edit these files by hand.",
    registry: "https://raw.githubusercontent.com/mflkee/metro-ui/main/public/r/{name}.json",
    files,
  };
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`fleet-ui: manifest written for ${Object.keys(files).length} vendored files`);
}

function check() {
  if (!existsSync(manifestPath)) {
    console.error("fleet-ui: fleet-ui.manifest.json is missing — run `npm run check:ui -- manifest`");
    return 1;
  }

  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const vendored = new Set(vendoredFiles().map(relative));
  const problems = [];

  for (const [file, expected] of Object.entries(manifest.files)) {
    const full = path.join(root, file);
    if (!existsSync(full)) {
      problems.push(`${file}: vendored file is gone (re-add the item or regenerate the manifest)`);
      continue;
    }
    if (hash(full) !== expected) {
      problems.push(
        `${file}: edited in place — change it in mflkee/metro-ui, then ` +
          `\`npx shadcn@latest add @metro/<item> --overwrite\` and \`npm run check:ui -- manifest\``,
      );
    }
  }

  const srcDir = path.join(root, "src");
  if (existsSync(srcDir)) {
    for (const file of walk(srcDir)) {
      const rel = relative(file);
      if (vendored.has(rel)) {
        continue;
      }
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, index) => {
        // A comment may name a colour to explain why it is not used.
        const isComment = /^\s*(\*|\/\/|\/\*)/.test(line);
        if (isComment) {
          return;
        }
        if (PALETTE_UTILITY.test(line)) {
          problems.push(`${rel}:${index + 1}: Tailwind palette colour — use a theme token (text-steel, var(--danger-text), …)`);
        }
        if (HEX_COLOUR.test(line) && !HEX_ALLOWED_IN.some((pattern) => pattern.test(rel))) {
          problems.push(`${rel}:${index + 1}: hardcoded colour — use a theme token`);
        }
      });
    }
  }

  // A Dockerfile that copies the app selectively must also copy the guard and its
  // manifest, or `npm run check:ui` fails inside the image and the deploy silently stops.
  // (Skipped inside the image, where the Dockerfile is not part of the build context.)
  const dockerfile = path.join(root, "Dockerfile");
  if (existsSync(dockerfile)) {
    const text = readFileSync(dockerfile, "utf8");
    // `COPY frontend/ ./` and `COPY . .` bring the whole tree along; anything else is a
    // list that can forget a file.
    const copiesEverything = /^COPY\s+(?:frontend\/|\.\/?)\s+\.\/?\s*$/m.test(text);
    if (!copiesEverything) {
      for (const needed of ["scripts", "fleet-ui.manifest.json"]) {
        if (!text.includes(needed)) {
          problems.push(
            `Dockerfile: the build copies the app selectively but never copies ${needed} — ` +
              "the image build will fail at `npm run check:ui`",
          );
        }
      }
    }
  }

  if (problems.length) {
    console.error(`fleet-ui: ${problems.length} problem(s):\n`);
    for (const problem of problems) {
      console.error(`  ${problem}`);
    }
    return 1;
  }

  console.log(
    `fleet-ui: ${Object.keys(manifest.files).length} vendored files unchanged, no hardcoded colours`,
  );
  return 0;
}

const args = process.argv.slice(2);
// `npm run check:ui -- manifest` arrives as ["check", "manifest"], so manifest wins.
const mode = args.includes("manifest") ? "manifest" : "check";
if (mode === "manifest") {
  writeManifest();
  process.exit(0);
}
if (mode === "check") {
  process.exit(check());
}
console.error(`fleet-ui: unknown mode in "${args.join(" ")}" (use check or manifest)`);
process.exit(2);
