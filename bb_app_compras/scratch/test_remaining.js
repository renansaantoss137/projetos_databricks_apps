const fs = require("fs");
const styles = fs.readFileSync("src/app/styles.css", "utf8");
const index = fs.readFileSync("src/app/index.html", "utf8");

console.log("Checking purple in styles.css:");
const purpleKeywords = ["purple", "violet", "#8b5cf6", "#a855f7", "#c084fc", "#7c3aed", "#6366f1", "#4f46e5"];
styles.split("\n").forEach((l, i) => {
  purpleKeywords.forEach(k => {
    if (l.toLowerCase().includes(k)) {
      console.log(`styles.css:${i+1}: ${l}`);
    }
  });
});

console.log("Checking purple in index.html:");
index.split("\n").forEach((l, i) => {
  purpleKeywords.forEach(k => {
    if (l.toLowerCase().includes(k)) {
      console.log(`index.html:${i+1}: ${l}`);
    }
  });
});

console.log("Checking 3b82f6 zero-offset box-shadow:");
styles.split("\n").forEach((l, i) => {
  if (l.includes("box-shadow") && (l.includes("3b82f6") || l.includes("59, 130, 246") || l.includes("59,130,246") || l.includes("0 0 "))) {
    console.log(`styles.css:${i+1}: ${l}`);
  }
});
index.split("\n").forEach((l, i) => {
  if (l.includes("box-shadow") && (l.includes("3b82f6") || l.includes("59, 130, 246") || l.includes("59,130,246") || l.includes("0 0 "))) {
    console.log(`index.html:${i+1}: ${l}`);
  }
});
