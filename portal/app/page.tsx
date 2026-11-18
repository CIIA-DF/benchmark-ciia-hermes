import fs from "fs";
import path from "path";

export default function Home() {
  const htmlPath = path.join(process.cwd(), "public", "index.html");
  let html = fs.readFileSync(htmlPath, "utf-8");

  // Injetar o HTML diretamente preservando estilos e scripts da landing page
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
