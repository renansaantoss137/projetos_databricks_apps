const fs = require("fs");
const styles = fs.readFileSync("src/app/styles.css", "utf8");
const lines = styles.split("\n");
lines.forEach((l, i) => {
  if (l.includes("13203a") || l.includes("7c3aed") || l.includes("rgba(124,58,237") || l.includes("0 0 6px") || l.includes("radial-gradient")) {
    console.log(`styles.css:${i+1}: ${l}`);
  }
});
