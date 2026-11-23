const { execSync } = require('child_process');
try {
  const res = execSync(`"C:\\Users\\renan.ferreira\\.gemini\\config\\skills\\impeccable\\scripts\\impeccable.cmd" detect --json src/app/index.html`, { encoding: 'utf8' });
  const json = JSON.parse(res);
  console.log("Total findings:", json.length);
  const map = {};
  json.forEach(f => {
    map[f.antipattern] = (map[f.antipattern] || 0) + 1;
  });
  console.log("Summary:", JSON.stringify(map, null, 2));
  console.log("\nFull list of findings:");
  json.forEach(f => {
    console.log(`- [${f.severity}] ${f.name} (${f.antipattern}): ${f.snippet}`);
  });
} catch (e) {
  if (e.stdout) {
    try {
      const json = JSON.parse(e.stdout);
      console.log("Total findings:", json.length);
      const map = {};
      json.forEach(f => {
        map[f.antipattern] = (map[f.antipattern] || 0) + 1;
      });
      console.log("Summary:", JSON.stringify(map, null, 2));
      console.log("\nFull list of findings:");
      json.forEach(f => {
        console.log(`- [${f.severity}] ${f.name} (${f.antipattern}): ${f.snippet}`);
      });
    } catch(err) {
      console.error("Parse error:", err, e.stdout);
    }
  } else {
    console.error(e);
  }
}
