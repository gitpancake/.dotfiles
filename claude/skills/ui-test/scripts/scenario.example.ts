import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { homedir } from "node:os"

const { mintToken, openCartageApp, pushEvidence, sandboxIdentity } = await import(
    join(homedir(), ".dotfiles/claude/skills/ui-test/scripts/cartageApp.ts")
)

const outDir = process.env.OUT_DIR ?? mkdtempSync(join(tmpdir(), "ui-test-"))
const url = process.env.DEV_ENV_URL
if (!url) throw new Error("DEV_ENV_URL is required: run /host-dev and pass the VM URL")
const token = process.env.DEV_ENV_TOKEN ?? mintToken(sandboxIdentity())

const app = await openCartageApp({ url, token, outDir })
try {
    await app.open("messages")
    await app.waitForText("Slack")
    await app.shot("01-messages-list")

    await app.open("settings")
    await app.click("Config Tables")
    await app.waitForText("Config Tables")
    await app.shot("02-config-tables")
} finally {
    await app.close()
}

console.log(`screenshots in ${outDir}`)

if (process.env.EVIDENCE_TICKET && process.env.EVIDENCE_PR) {
    const { branch, images } = pushEvidence({
        ticket: process.env.EVIDENCE_TICKET,
        prNumber: Number(process.env.EVIDENCE_PR),
        dir: outDir,
    })
    console.log(`pushed ${branch}`)
    for (const image of images) console.log(image.markdown(image.file))
}
