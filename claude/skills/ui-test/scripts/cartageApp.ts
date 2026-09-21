import { createRequire } from "node:module"
import { execFileSync } from "node:child_process"
import { existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { homedir } from "node:os"
import type { Browser, BrowserContext, Locator, Page } from "playwright"

export type WindowType =
    | "setup"
    | "explorer"
    | "tables"
    | "reports"
    | "wilson"
    | "mail"
    | "messages"
    | "phone"
    | "tasks"
    | "warehouseScheduling"
    | "freightDashboard"
    | "cartagePay"
    | "settings"
    | "document"
    | "report"
    | "template"

const WINDOW_TITLES: Partial<Record<WindowType, string>> = {
    setup: "Setup",
    explorer: "Explorer",
    tables: "Tables",
    reports: "Reports",
    wilson: "Wilson",
    mail: "Mail",
    messages: "Messages",
    phone: "Phone",
    tasks: "Tasks",
    warehouseScheduling: "Docks",
    freightDashboard: "Dashboard",
    cartagePay: "Wallet",
    settings: "Settings",
}

const DOCK_SELECTOR = '[aria-label="Application dock"]'
const WINDOW_SELECTOR = ".desktop-window"
const DESKTOP_STORE_KEY_PREFIX = "desktop-store"
const DESKTOP_READY_TIMEOUT_MS = 180_000
const WINDOW_OPEN_TIMEOUT_MS = 60_000

const PRIVATE_ENV_PATH = join(homedir(), ".claude", ".env")

function privateEnv(key: string): string | undefined {
    if (process.env[key]) return process.env[key]
    if (!existsSync(PRIVATE_ENV_PATH)) return undefined
    const line = readFileSync(PRIVATE_ENV_PATH, "utf8")
        .split("\n")
        .find(l => l.startsWith(`${key}=`))
    return line?.slice(key.length + 1).trim().replace(/^["']|["']$/g, "")
}

export function sandboxIdentity(): { orgId: string; userId: string } {
    const orgId = privateEnv("UI_TEST_ORG_ID")
    const userId = privateEnv("UI_TEST_USER_ID")
    if (!orgId || !userId) {
        throw new Error(`UI_TEST_ORG_ID and UI_TEST_USER_ID must be set in the environment or ${PRIVATE_ENV_PATH}`)
    }
    return { orgId, userId }
}

function repoRoot(cwd = process.cwd()): string {
    return execFileSync("git", ["rev-parse", "--show-toplevel"], { cwd, encoding: "utf8" }).trim()
}

function loadPlaywright(cwd?: string): typeof import("playwright") {
    const root = repoRoot(cwd)
    const requireFromRepo = createRequire(join(root, "package.json"))
    return requireFromRepo("playwright")
}

export interface OpenCartageAppOptions {
    url: string
    token: string
    outDir: string
    cwd?: string
    viewport?: { width: number; height: number }
    headless?: boolean
}

export interface CartageApp {
    page: Page
    context: BrowserContext
    browser: Browser
    baseUrl: string
    open: (windowType: WindowType, params?: Record<string, string>) => Promise<void>
    waitForText: (text: string, opts?: { exact?: boolean; timeoutMs?: number }) => Promise<void>
    click: (text: string, opts?: { exact?: boolean; timeoutMs?: number }) => Promise<void>
    /** The one match of `selector` that is actually on top at its own center — skips duplicates hidden under the desktop canvas. */
    topmost: (selector: string, opts?: { timeoutMs?: number }) => Promise<Locator>
    shot: (name: string) => Promise<string>
    bodyText: () => Promise<string>
    close: () => Promise<void>
}

export async function openCartageApp(options: OpenCartageAppOptions): Promise<CartageApp> {
    const { chromium } = loadPlaywright(options.cwd)
    const baseUrl = options.url.replace(/\/$/, "")
    mkdirSync(options.outDir, { recursive: true })

    const browser = await chromium.launch({ headless: options.headless ?? true })
    const context = await browser.newContext({
        viewport: options.viewport ?? { width: 1440, height: 900 },
    })
    await context.addCookies([
        {
            name: "token",
            value: options.token,
            domain: new URL(baseUrl).hostname,
            path: "/",
            httpOnly: false,
            secure: true,
            sameSite: "Lax",
        },
    ])
    const page = await context.newPage()

    async function assertNotOnLogin() {
        if (page.url().includes("/login")) {
            throw new Error(`Redirected to /login — token rejected or expired for ${baseUrl}`)
        }
    }

    async function waitForDesktop() {
        await page.locator(DOCK_SELECTOR).first().waitFor({ timeout: DESKTOP_READY_TIMEOUT_MS })
        await assertNotOnLogin()
    }

    async function clearPersistedDesktop() {
        if (!page.url().startsWith(baseUrl)) return
        await page.evaluate(prefix => {
            Object.keys(localStorage)
                .filter(key => key.startsWith(prefix))
                .forEach(key => localStorage.removeItem(key))
        }, DESKTOP_STORE_KEY_PREFIX)
    }

    async function open(windowType: WindowType, params: Record<string, string> = {}) {
        await clearPersistedDesktop()
        const search = new URLSearchParams({ w: windowType, restore: "false", ...params })
        await page.goto(`${baseUrl}/?${search.toString()}`, {
            waitUntil: "domcontentloaded",
            timeout: DESKTOP_READY_TIMEOUT_MS,
        })
        await waitForDesktop()
        const title = WINDOW_TITLES[windowType]
        const windowLocator = title
            ? page.locator(WINDOW_SELECTOR, { hasText: title }).first()
            : page.locator(WINDOW_SELECTOR).first()
        await windowLocator.waitFor({ timeout: WINDOW_OPEN_TIMEOUT_MS })
    }

    async function waitForText(text: string, opts: { exact?: boolean; timeoutMs?: number } = {}) {
        await page
            .getByText(text, { exact: opts.exact ?? true })
            .first()
            .waitFor({ timeout: opts.timeoutMs ?? WINDOW_OPEN_TIMEOUT_MS })
    }

    async function click(text: string, opts: { exact?: boolean; timeoutMs?: number } = {}) {
        await page
            .getByText(text, { exact: opts.exact ?? true })
            .first()
            .click({ timeout: opts.timeoutMs ?? WINDOW_OPEN_TIMEOUT_MS })
    }

    async function topmost(selector: string, opts: { timeoutMs?: number } = {}): Promise<Locator> {
        const deadline = Date.now() + (opts.timeoutMs ?? WINDOW_OPEN_TIMEOUT_MS)
        while (Date.now() < deadline) {
            const index = await page.evaluate(sel => {
                return Array.from(document.querySelectorAll(sel)).findIndex(el => {
                    const box = el.getBoundingClientRect()
                    if (box.width === 0 || box.height === 0) return false
                    const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2)
                    return !!hit && (hit === el || el.contains(hit))
                })
            }, selector)
            if (index >= 0) return page.locator(selector).nth(index)
            await page.waitForTimeout(250)
        }
        throw new Error(`topmost: no hit-testable match for ${selector}`)
    }

    async function shot(name: string): Promise<string> {
        const path = join(options.outDir, name.endsWith(".png") ? name : `${name}.png`)
        await page.screenshot({ path })
        return path
    }

    async function bodyText(): Promise<string> {
        return page.evaluate(() => document.body.innerText)
    }

    async function close() {
        await browser.close()
    }

    return { page, context, browser, baseUrl, open, waitForText, click, topmost, shot, bodyText, close }
}

export function mintToken(options: { userId: string; orgId: string; cwd?: string }): string {
    const cwd = repoRoot(options.cwd)
    const output = execFileSync(
        "bun",
        ["run", "script", "--", "generateDevEnvToken", "--userId", options.userId, "--orgId", options.orgId],
        { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }
    )
    const token = output.match(/eyJ[A-Za-z0-9._-]+/)?.[0]
    if (!token) throw new Error(`generateDevEnvToken printed no JWT:\n${output}`)
    return token
}

export interface EvidenceImage {
    file: string
    url: string
    markdown: (caption: string) => string
}

export function pushEvidence(options: {
    ticket: string
    prNumber: number
    dir: string
    cwd?: string
    remote?: string
}): { branch: string; images: EvidenceImage[] } {
    const cwd = repoRoot(options.cwd)
    const remote = options.remote ?? "origin"
    const files = readdirSync(options.dir)
        .filter(f => f.endsWith(".png"))
        .sort()
    if (files.length === 0) throw new Error(`no .png files in ${options.dir}`)

    const git = (args: string[], input?: string) =>
        execFileSync("git", args, { cwd, encoding: "utf8", input }).trim()

    const treeLines = files
        .map(f => {
            const blob = git(["hash-object", "-w", join(options.dir, f)])
            return `100644 blob ${blob}\t${f}`
        })
        .join("\n")
    const tree = git(["mktree"], `${treeLines}\n`)
    const commit = git([
        "commit-tree",
        tree,
        "-m",
        `${options.ticket.toUpperCase()}: manual-test evidence for PR #${options.prNumber} (no code changes)`,
    ])

    const baseBranch = `evidence/${options.ticket.toLowerCase()}-manual-test-screenshots`
    const branch = firstFreeEvidenceBranch({ cwd, remote, baseBranch, git })
    git(["push", remote, `${commit}:refs/heads/${branch}`])

    const repoSlug = git(["remote", "get-url", remote])
        .replace(/^.*github\.com[:/]/, "")
        .replace(/\.git$/, "")
    const images = files.map(f => {
        const url = `https://github.com/${repoSlug}/blob/${branch}/${f}?raw=true`
        return { file: f, url, markdown: (caption: string) => `![${caption}](${url})` }
    })
    return { branch, images }
}

function firstFreeEvidenceBranch(options: {
    cwd: string
    remote: string
    baseBranch: string
    git: (args: string[]) => string
}): string {
    const taken = new Set(
        options
            .git(["ls-remote", "--heads", options.remote, `${options.baseBranch}*`])
            .split("\n")
            .map(line => line.split("\t")[1]?.replace("refs/heads/", ""))
            .filter(Boolean)
    )
    if (!taken.has(options.baseBranch)) return options.baseBranch
    for (let version = 2; version < 100; version++) {
        const candidate = `${options.baseBranch}-v${version}`
        if (!taken.has(candidate)) return candidate
    }
    throw new Error(`too many evidence branches for ${options.baseBranch}`)
}
