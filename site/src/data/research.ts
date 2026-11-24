// The Center's research agenda. Homepage uses `short` + `teaser`; the Research page uses `name`,
// `question`, `summary` (HTML), then a "Read more" line built from `more` (links) and `topics` (links to the
// papers page with that topic highlighted on the map), or `note` (HTML) for a pillar with nothing to read yet.
import { url } from '../lib/url';

// Plain text (page descriptions) and HTML (on-page, with emphasis).
export const mission =
  'We aim to develop a first-principles, quantitative science of how intelligence is learned, represented, interpreted, computed, and organized in brains and machines.';
export const missionHtml =
  'We aim to develop a <em>first-principles, quantitative science</em> of how intelligence is <em>learned, represented, interpreted, computed, and organized</em> in brains and machines.';

type Link = { label: string; url: string };
type Topic = { key: string; label: string }; // key: a paper topic (lib/topics.ts); label: how the sentence names it

export const pillars: {
  id: string;
  short: string;
  name: string;
  teaser: string;
  question: string;
  summary: string;
  more: Link[];
  topics: Topic[];
  note?: string;
}[] = [
  {
    id: 'learning-mechanics',
    short: 'Learning mechanics',
    name: 'Learning mechanics',
    teaser: 'How do neural networks learn?',
    question: 'How do neural networks learn?',
    summary:
      'There is reason to believe that <a href="https://arxiv.org/abs/2604.21691">there will be a scientific theory of deep learning</a>, and that its development and final form will resemble a branch of physics. How do we describe learning in neural networks, with simple mathematics that makes correct predictions in simple experiments? How can we apply this fundamental science to understand the AI systems we interact with?',
    more: [{ label: 'learningmechanics.pub', url: 'https://learningmechanics.pub/' }],
    topics: [{ key: 'learning-mech', label: 'learning mechanics' }],
  },
  {
    id: 'data-and-representations',
    short: 'Data and representations',
    name: 'Data and representations',
    teaser: 'How does data shape learning?',
    question: 'What structure is latent in data, and how is it reflected in neural network representations?',
    summary:
      'All the capabilities of modern AI, and of their internal structure, must ultimately have their origin in the data on which they were trained. What structure is latent in data, and how do we measure it—and how is this structure extracted by learning systems and encoded in weights and hidden representations? How do biological and artificial learning systems differ in this regard?',
    more: [
      {
        label: 'Data Structure, Symmetries, and Neural Network Representations',
        url: url('blog/data-structure-symmetries-representations/'),
      },
    ],
    topics: [
      { key: 'learning-mech', label: 'learning mechanics' },
      { key: 'neuromorphic', label: 'neuromorphic computing' },
    ],
  },
  {
    id: 'interpretability',
    short: 'Interpretability and neural computation',
    name: 'Interpretability and neural computation',
    teaser: 'How do biological and artificial networks compute?',
    question:
      'How do we mathematically describe computation inside a neural network, whether biological or artificial?',
    summary:
      'What are the right mathematical abstractions, decompositions, and tools for post-hoc understanding of trained neural networks—biological or artificial? How can we connect notions of sparsity and symmetry to the messy world inside a neural network? What does this imply about intelligent systems, including us?',
    more: [],
    topics: [
      { key: 'representation', label: 'sparse coding' },
      { key: 'vision', label: 'vision science' },
      { key: 'neuro-data', label: 'neural data' },
      { key: 'neuro-theory', label: 'theoretical neuroscience' },
    ],
  },
  {
    id: 'dynamics',
    short: 'Dynamics and computation',
    name: 'Dynamics and computation',
    teaser: 'How does intelligence unfold in time?',
    question:
      'How does intelligent computation unfold at test-time, in LLM reasoning, diffusion models, RNNs, and biological systems?',
    summary:
      'Intelligence is not merely an excellent function map executed once: in both brains and AI, intelligence unfolds over time. How? What principles shape this unfolding, and what laws does it obey? How is information gathered, stored, transformed, and used through time?',
    more: [],
    topics: [
      { key: 'physics', label: 'statistical physics' },
      { key: 'physical-computing', label: 'physical computing' },
      { key: 'ml-practice', label: 'ML practice' },
      { key: 'neuro-theory', label: 'theoretical neuroscience' },
    ],
  },
  {
    id: 'collective-intelligence',
    short: 'Collective intelligence',
    name: 'Collective intelligence',
    teaser: 'What laws emerge when agents interact?',
    question: 'How can we empirically describe the collective behavior of many agents?',
    summary:
      'It is already clear that many AI agents acting as a swarm are vastly more capable together than separate. The same is true of many animals. Why? How can we mathematically characterize this collective intelligence? What new laws emerge when many agents interact?',
    more: [],
    topics: [],
    note: `This is a new direction for the Center, and we have no published work on the subject. <a href="${url('work-here/')}">Come here and do it!</a>`,
  },
];
