const fs = require("fs");
const styles = fs.readFileSync("src/app/styles.css", "utf8");
const lines = styles.split("\n");
lines.forEach((l, i) => {
  if (l.includes("mc-badge") || l.includes("mc-desc") || l.includes("13203a") || l.includes("font-size") && l.includes("html")) {
    console.log(`styles.css:${i+1}: ${l}`);
  }
});

const index = fs.readFileSync("src/app/index.html", "utf8");
const ilines = index.split("\n");
ilines.forEach((l, i) => {
  if (l.includes("13203a") || l.includes("hero-eyebrow")) {
    console.log(`index.html:${i+1}: ${l}`);
  }
});
