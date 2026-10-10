"""Escaped multilingual text and automatic bidi direction in native inputs."""

from html import escape


def text_html(text):
    return (
        "<div dir='auto' style='white-space:pre-wrap;unicode-bidi:plaintext;text-align:start'>"
        + escape(text)
        + "</div>"
    )


INPUT_DIRECTION = """
<script>
(() => {
  const apply = () => document.querySelectorAll('textarea,input[type="text"]').forEach(el => {
    if (el.getAttribute('dir') !== 'auto') el.setAttribute('dir', 'auto');
    el.style.textAlign = 'start';
  });
  apply();
  if (!window.pinuiDirectionObserver) {
    window.pinuiDirectionObserver = new MutationObserver(apply);
    window.pinuiDirectionObserver.observe(document.body, {childList: true, subtree: true});
  }
})();
</script>
"""
