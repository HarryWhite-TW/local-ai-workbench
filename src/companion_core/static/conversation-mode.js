/* Capture the presentation choice before existing navigation normalizes hashes. */
window.nexusComparisonLayout = new URLSearchParams(location.hash.split('?')[1]).get('layout') === 'ux02';
