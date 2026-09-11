import { readdirSync, readFileSync } from "node:fs";
import { Database } from "bun:sqlite";
import assert from "node:assert/strict";
const { Server } = await import("/app/build/server/index.js");
const { manifest } = await import("/app/build/server/manifest.js");
await new Server(manifest).init({ env: process.env });
const dir = "/app/build/server/chunks/";
const file = readdirSync(dir).find(n => n.endsWith(".js") && readFileSync(dir+n,"utf8").includes("async function getConfig("));
assert(file);
const code = readFileSync(dir+file,"utf8");
const mod = await import(dir+file);
const fn = name => { const alias=code.match(new RegExp("\\b"+name+" as (\\w+)")); assert(alias,name); return mod[alias[1]]; };
const mode = process.argv[2];
const db = new Database("/config/data/otpravkarr.sqlite");
if (mode === "write") {
  await fn("setConfig")("packaging_config_probe", "disposable-config-value", true);
  const encrypted = await fn("encrypt")("disposable-credential-value", "credential-encryption");
  await fn("setConfig")("packaging_credential_probe", encrypted, false);
}
if (mode === "wrong") {
  await assert.rejects(() => fn("getConfig")("packaging_config_probe"));
  const credential = await fn("getConfig")("packaging_credential_probe");
  await assert.rejects(() => fn("decrypt")(credential,"credential-encryption"));
  console.log(JSON.stringify({ wrongKeyRejected: true }));
} else {
  assert.equal(await fn("getConfig")("packaging_config_probe"), "disposable-config-value");
  const credential = await fn("getConfig")("packaging_credential_probe");
  assert.equal(await fn("decrypt")(credential,"credential-encryption"), "disposable-credential-value");
  const row = db.query("SELECT value, encrypted FROM config WHERE key='packaging_config_probe'").get();
  assert.equal(row.encrypted, 1); assert.notEqual(row.value,"disposable-config-value");
  assert.notEqual(credential,"disposable-credential-value");
  assert.equal(db.query("PRAGMA integrity_check").get().integrity_check,"ok");
  console.log(JSON.stringify({ configDecrypted:true,credentialDecrypted:true,encryptedAtRest:true,integrity:true,migrations:db.query("SELECT count(*) AS n FROM _migrations").get().n }));
}
db.close();
