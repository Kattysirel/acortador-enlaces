const API_URL = "http://44.209.156.144:8000";

const form = document.getElementById("form");
const urlInput = document.getElementById("url");
const errorBox = document.getElementById("error");
const resultBox = document.getElementById("result");
const shortInput = document.getElementById("short");
const copyBtn = document.getElementById("copy");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.textContent = "";
  resultBox.classList.add("hidden");

  try {
    new URL(urlInput.value);
  } catch {
    errorBox.textContent = "La URL no es válida. Incluye http:// o https://";
    return;
  }

  try {
    const res = await fetch(`${API_URL}/shorten`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ original_url: urlInput.value }),
    });
    if (!res.ok) {
      errorBox.textContent = "El servidor rechazó la URL. Revisa que sea válida.";
      return;
    }
    const data = await res.json();
    shortInput.value = data.short_url;
    resultBox.classList.remove("hidden");
  } catch {
    errorBox.textContent = "No se pudo conectar con el backend.";
  }
});

copyBtn.addEventListener("click", () => {
  shortInput.select();
  document.execCommand("copy");
  copyBtn.textContent = "¡Copiado!";
  setTimeout(() => (copyBtn.textContent = "Copiar"), 1500);
});