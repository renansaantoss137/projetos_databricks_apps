const fs = require("fs");
const styles = fs.readFileSync("src/app/styles.css", "utf8");
const lines = styles.split("\n");
lines.forEach((l, i) => {
  if (l.includes("box-shadow") && (l.includes("64748b") || l.includes("100, 116, 139") || l.includes("100,116,139") || l.includes("15, 23, 42") || l.includes("2, 132, 199") || l.includes("37, 99, 235"))) {
    console.log(`styles.css:${i+1}: ${l}`);
  }
});
