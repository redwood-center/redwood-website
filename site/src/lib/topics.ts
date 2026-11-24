// Topic colors, shared by the paper map and the paper list. Colors come from the validated categorical palette
// (dataviz reference), assigned by meaning so related topics look related (Jamie, 2026-10-27): neural data pink like
// the brain, vision orange, theory red, sparse coding yellow, physics blue, learning mechanics green with ML practice
// a pale green; neuromorphic fuchsia-purple with physical computing a pale lavender. Gray = other.
export const OTHER_COLOR = '#9aa49e';
export const TOPIC_COLORS: Record<string, string> = {
  'neuro-data': '#e87ba4', vision: '#eb6834', 'neuro-theory': '#e34948', representation: '#eda100',
  physics: '#2a78d6', 'learning-mech': '#008300', 'ml-practice': '#9fd49b', neuromorphic: '#a33fc0',
  'physical-computing': '#c4b6f2', other: OTHER_COLOR,
};
// Legend order: rainbow (red -> orange -> yellow -> greens -> blue -> lavender -> fuchsia -> pink), then Other.
export const TOPIC_ORDER = ['neuro-theory', 'vision', 'representation', 'learning-mech', 'ml-practice', 'physics',
  'physical-computing', 'neuromorphic', 'neuro-data', 'other'];
// The PI view uses its own, more saturated rainbow (so it doesn't read as the topic colors), in People-page order.
export const PI_RAINBOW = ['#d62828', '#f77f00', '#e9c400', '#2b9348', '#1d5fd1', '#7b2cbf'];
