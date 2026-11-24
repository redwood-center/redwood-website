# Paper categories

Jamie's edited set (2026-10-27). The labeling pass reads this file: one `##` section per category, as
`## <id>: <Name>`, then a description. "Not" lines say where borderline papers go instead. Keep the ids stable
(they're what review decisions store); rename, reword, add or delete sections freely.

Every paper gets exactly one category: the one that best names what the paper is *for*, not every topic it touches.
Papers that fit none of these well go in `other`.

## learning-mech: Learning mechanics

Understanding how networks train, learn, generalize: dynamics, kernels, feature learning, landscapes. Jamie's
research agenda. Learning dynamics and solvable models, kernel and infinite-width limits (NTK, eigenlearning),
feature learning, loss landscapes and optimization, scaling and overfitting, what trained networks learn and why.
The aim is understanding, not a better system.

- Not: learning principles derived from natural-signal statistics in the sparse-coding tradition (-> Sparse coding).
- Examples: The Eigenlearning Framework; Alternating Gradient Flows; Closed-form training dynamics of word2vec;
  SGD Can Converge to Local Maxima; Benign, Tempered, or Catastrophic; Quantifying Elicitation of Latent
  Capabilities in Language Models.

## representation: Sparse coding etc.

Efficient representations learned from the structure of natural signals; the Olshausen-Field tradition. Sparse
coding, efficient coding, dictionary learning, manifolds and symmetries (equivariance, invariance, Lie groups,
bispectra) in images, sound and color, and unsupervised and generative learning in that spirit (energy-based models,
score matching, source separation).

- Not: a model whose point is explaining a specific visual phenomenon or measurement (-> Vision science).
- Examples: Group Equivariant Sparse Coding; The Sparse Manifold Transform; Emergence of strategic cone weighting
  from efficient coding of spatiochromatic natural images; Bispectral Neural Networks; Transformer visualization
  via dictionary learning.

## neuromorphic: Neuromorphic computing

Vector symbolic architectures, resonator networks, binding, spiking/Loihi algorithms: computing with
high-dimensional distributed representations, and algorithms for spiking and neuromorphic chips. Includes the theory
of reservoir computing and of memory in distributed and oscillator networks, and models of brain circuits built on
these ideas (binding and residue codes in the hippocampal-entorhinal system).

- Not: physical substrates themselves (-> Physical computing).
- Examples: Resonator Networks 1 and 2; Vector Symbolic Architectures as a Computing Framework for Emerging Hardware;
  Computing With Residue Numbers in High-Dimensional Representation; Perceptron Theory Can Predict the Accuracy of
  Neural Networks; Towards a Comprehensive Theory of Reservoir Computing.

## physical-computing: Physical computing

Physical substrates: analog memory, memristors, optics, Ising machines, oscillators, and coding schemes designed
around such devices' noise and imprecision.

- Not: wearable eye trackers or other experimental rigs (-> the science they serve, usually Vision science).
- Examples: Analog Coding in Emerging Memory Systems; Design of optical neural networks with component imprecisions;
  Efficient optimization with higher-order Ising machines.

## vision: Vision science

Perception and the visual system: eye movements, psychophysics, visual cortex, retina/V1 models. Fixational drift,
saccades, nystagmus, vestibular and oculomotor control, recordings from visual cortex in behaving animals, models
built to explain what is measured, and the tools built for these experiments (eye and head tracking).

- Not: general principles of efficient coding illustrated on images (-> Sparse coding).
- Examples: Detailed characterization of neural selectivity in free viewing primates; High-acuity vision from
  retinal image motion; A discontinuity in motion perception during fixational drift.

## neuro-theory: Theoretical neuroscience

Theory of how brains code, store and integrate information: population coding and shared noise, attractor dynamics
and replay, memory and structural plasticity, integrated information in brain networks.

- Not: models built on vector symbolic architectures, reservoir computing or oscillator memories (-> Neuromorphic).
- Not: analysis of recorded neural data or methods for it (-> Neural data).
- Examples: Replay as wavefronts and theta sequences as bump oscillations in a grid cell attractor network;
  Heterogeneous synaptic weighting improves neural coding in the presence of common noise; Information integration
  in large brain networks.

## neuro-data: Neural data

ECoG, spike sorting, connectomics, sparse regression, data standards (NWB). Measuring and analyzing brain activity
and the statistics and infrastructure behind it (Union of Intersections, latent-variable and Gaussian-process
models, HDMF, open-data tools), including machine learning built as a tool for neuroscience data (sleep scoring,
speech decoding).

- Not: theory of neural computation (-> Theoretical neuroscience).
- Examples: Human sensorimotor cortex control of directly measured vocal tract movements; Sparse, predictive, and
  interpretable functional connectomics with UoILasso; NWB:N 2.0.

## physics: Statistical physics

Nonequilibrium thermodynamics, optimal protocols, active matter, costs of computation. Stochastic thermodynamics,
heat engines, fluctuation theorems, quantum state control, and the thermodynamic and information-theoretic costs of
computation.

- Examples: Optimal finite-time Brownian Carnot engine; Beyond Linear Response: Equivalence between Thermodynamic
  Geometry and Optimal Transport; The Entropy of Floating-Point Numbers.

## ml-practice: ML practice

Machine learning as it is practiced: new methods and applications built to work better rather than to explain why
learning works (test-time adaptation, continual learning, video coding and compression, generative samplers),
benchmarks and datasets, hyperparameter tuning, reinforcement-learning environments, and ML infrastructure.

- Not: understanding how networks learn (-> Learning mechanics).
- Examples: Avalon; Tune As You Scale; Tent; Automatically inferring task context for continual learning;
  DeepMovie; Hangul Fonts Dataset.

## other: Other

Anything that doesn't fit well into an above category: machine learning for other sciences (omics, proteins, CT,
detectors) and the odd one out.
