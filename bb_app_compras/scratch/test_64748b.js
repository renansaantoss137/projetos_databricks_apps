const fs = require("fs");
const styles = fs.readFileSync("src/app/styles.css", "utf8");
const lines = styles.split("\n");
lines.forEach((l, i) => {
  if (l.includes("64748b") || l.includes("64, 116, 139") || l.includes("64,116,139")) {
    console.log(`styles.css:${i+1}: ${l}`);
  }
});
