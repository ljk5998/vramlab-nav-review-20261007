// Temporary preview fixture only. The production search bundle is unchanged.
// A query parameter opts into one failure; Retry uses the real hosted index.
(() => {
  const mode = new URLSearchParams(window.location.search).get('__qa_failure');
  if (!['http-error', 'invalid-json', 'network', 'timeout'].includes(mode)) return;
  const nativeFetch = window.fetch.bind(window);
  const note = document.createElement('p');
  note.textContent = `QA fixture: one controlled ${mode} failure. Retry loads the real search index.`;
  note.setAttribute('role', 'note');
  document.getElementById('searchbox')?.before(note);
  window.fetch = (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
    if (!url.pathname.endsWith('/index.json')) return nativeFetch(input, options);
    window.fetch = nativeFetch;
    if (mode === 'http-error') {
      return nativeFetch(new URL('__qa__/missing-index.json', url).href, options);
    }
    if (mode === 'invalid-json') {
      return Promise.resolve(new Response('{invalid', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (mode === 'network') return Promise.reject(new TypeError('Controlled QA network rejection'));
    return new Promise((resolve, reject) => {
      const abort = () => reject(new DOMException('Controlled QA pending request aborted', 'AbortError'));
      if (options.signal?.aborted) abort();
      else options.signal?.addEventListener('abort', abort, { once: true });
    });
  };
})();
