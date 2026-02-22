/**
 * Finance Triage Agent — Frontend Scripts
 * Live search debounce for inbox search input
 */

(function() {
    const doc = window.parent.document;
    const inp = doc.querySelector('input[aria-label="Search"]');
    if (!inp || inp.dataset.liveSearch) return;
    inp.dataset.liveSearch = '1';
    let timer = null;
    inp.addEventListener('input', function() {
        clearTimeout(timer);
        timer = setTimeout(function() {
            // Simulate pressing Enter to trigger Streamlit rerun
            inp.dispatchEvent(new KeyboardEvent('keydown',  {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
            inp.dispatchEvent(new KeyboardEvent('keyup',    {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
            inp.dispatchEvent(new KeyboardEvent('keypress', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
        }, 400);
    });
})();
