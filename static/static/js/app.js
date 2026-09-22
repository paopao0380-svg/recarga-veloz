// Registrar Service Worker (PWA) - estilo Enlace Escolar
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((reg) => console.log('Recarga Veloz SW registrado', reg.scope))
      .catch((err) => console.log('SW no registrado', err));
  });
}
