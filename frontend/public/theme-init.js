// Apply the theme before first paint (external file to satisfy the CSP); light is the default.
// The server stamps the saved theme on <html data-theme>; localStorage covers pages served without it.
(function () {
  var root = document.documentElement;
  var theme = root.getAttribute("data-theme");
  try {
    theme = theme || localStorage.getItem("rgcopy-theme");
  } catch (e) {
    // storage may be unavailable
  }
  theme = theme || "light";
  var dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  root.classList.toggle("dark", dark);
})();
