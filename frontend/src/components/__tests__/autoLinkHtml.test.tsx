/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { AutoLinkHtml } from '../autoLink';
import type { EntityKind } from '../entities';

const kinds = new Map<string, EntityKind>();

function firstImg(html: string): HTMLImageElement | null {
  const { container } = render(<AutoLinkHtml html={html} kinds={kinds} />);
  return container.querySelector('img');
}

describe('AutoLinkHtml <img> allowlist', () => {
  it('renders an image with a data:image/ src', () => {
    const src = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB';
    const img = firstImg(`<img src="${src}" alt="diagram">`);
    expect(img).not.toBeNull();
    expect(img!.getAttribute('src')).toBe(src);
  });

  it('renders an image with a same-origin relative src', () => {
    const img = firstImg('<img src="/images/pump.png" alt="pump">');
    expect(img).not.toBeNull();
    expect(img!.getAttribute('src')).toBe('/images/pump.png');
  });

  it.each([
    ['javascript:alert(1)', 'javascript URL'],
    ['java\tscript:alert(1)', 'javascript URL with a control character'],
    ['vbscript:msgbox(1)', 'vbscript URL'],
    ['//evil.example/x.png', 'protocol-relative URL'],
    ['https://evil.example/x.png', 'absolute remote URL'],
    ['data:text/html,<script>alert(1)</script>', 'non-image data URL'],
    [' https://evil.example/x.png', 'absolute remote URL behind a leading space'],
    ['  javascript:alert(1)', 'javascript URL behind leading spaces'],
    ['\u000bhttps://evil.example/x.png', 'absolute remote URL behind a vertical tab'],
    ['\u000c https://evil.example/x.png', 'absolute remote URL behind a form feed'],
  ])('does not render an image for %s', (src) => {
    expect(firstImg(`<img src="${src}">`)).toBeNull();
  });

  it('carries only src and alt, dropping every other attribute', () => {
    const img = firstImg(
      '<img src="data:image/png;base64,abc" alt="diagram" onerror="alert(1)" title="sneaky" crossorigin="use-credentials">',
    );
    expect(img).not.toBeNull();
    expect(img!.getAttribute('src')).toBe('data:image/png;base64,abc');
    expect(img!.getAttribute('alt')).toBe('diagram');
    expect(img!.hasAttribute('onerror')).toBe(false);
    expect(img!.hasAttribute('title')).toBe(false);
    expect(img!.hasAttribute('crossorigin')).toBe(false);
  });

  it('omits alt entirely when the source has none', () => {
    const img = firstImg('<img src="/images/pump.png">');
    expect(img).not.toBeNull();
    expect(img!.hasAttribute('alt')).toBe(false);
  });
});
