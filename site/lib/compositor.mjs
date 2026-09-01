const PALETTE_REVISION = 'oklch-five-anchor-browser-v06';
const PALETTE_STOPS = Object.freeze([
  ['shadow', 0.22, 0.08],
  ['midtone', 0.42, 0.14],
  ['highlight', 0.61, 0.11],
  ['specular', 0.68, 0.09],
]);
const LUT_ANCHORS = Object.freeze([0, 32, 128, 224, 255]);
const FACE_BASE_ROLES = new Set(['earless_head_body', 'face_expression_base']);


export class CompositorError extends Error {
  constructor(message) {
    super(message);
    this.name = 'CompositorError';
  }
}


function clampByte(value) {
  return Math.max(0, Math.min(255, Math.round(value)));
}


function normalizeHue(hue) {
  if (!Number.isFinite(hue)) throw new CompositorError('Hair hue must be a finite number');
  return Math.round(((hue % 360) + 360) % 360);
}


function linearToSrgb(value) {
  return value <= 0.0031308
    ? 12.92 * value
    : 1.055 * (value ** (1 / 2.4)) - 0.055;
}


function oklchToSrgb8(lightness, chroma, hueDegrees) {
  const hue = hueDegrees * Math.PI / 180;
  const a = chroma * Math.cos(hue);
  const b = chroma * Math.sin(hue);
  const lRoot = lightness + 0.3963377774 * a + 0.2158037573 * b;
  const mRoot = lightness - 0.1055613458 * a - 0.0638541728 * b;
  const sRoot = lightness - 0.0894841775 * a - 1.2914855480 * b;
  const lValue = lRoot ** 3;
  const mValue = mRoot ** 3;
  const sValue = sRoot ** 3;
  const linear = [
    4.0767416621 * lValue - 3.3077115913 * mValue + 0.2309699292 * sValue,
    -1.2684380046 * lValue + 2.6097574011 * mValue - 0.3413193965 * sValue,
    -0.0041960863 * lValue - 0.7034186147 * mValue + 1.7076147010 * sValue,
  ];
  return linear.map((channel) => clampByte(linearToSrgb(channel) * 255));
}


export function deriveHairPalette(hue) {
  const hueDegrees = normalizeHue(hue);
  const stops = {};
  for (const [name, lightness, chroma] of PALETTE_STOPS) {
    stops[name] = Object.freeze({
      oklch: Object.freeze([lightness, chroma, hueDegrees]),
      srgb8: Object.freeze(oklchToSrgb8(lightness, chroma, hueDegrees)),
    });
  }
  return Object.freeze({
    algorithmRevision: PALETTE_REVISION,
    hueDegrees,
    stops: Object.freeze(stops),
  });
}


export function buildLuminanceLut(palette) {
  const colours = [
    [0, 0, 0],
    palette.stops.shadow.srgb8,
    palette.stops.midtone.srgb8,
    palette.stops.highlight.srgb8,
    palette.stops.specular.srgb8,
  ];
  const lut = new Uint8ClampedArray(256 * 3);
  for (let segment = 0; segment < LUT_ANCHORS.length - 1; segment += 1) {
    const start = LUT_ANCHORS[segment];
    const end = LUT_ANCHORS[segment + 1];
    for (let index = start; index <= end; index += 1) {
      const weight = (index - start) / (end - start);
      for (let channel = 0; channel < 3; channel += 1) {
        lut[index * 3 + channel] = (
          colours[segment][channel] * (1 - weight)
          + colours[segment + 1][channel] * weight
        );
      }
    }
  }
  return lut;
}


function srgbToLinear(value) {
  const normalized = value / 255;
  return normalized <= 0.04045
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4;
}


function luminanceIndex(red, green, blue) {
  const linear = (
    0.2126 * srgbToLinear(red)
    + 0.7152 * srgbToLinear(green)
    + 0.0722 * srgbToLinear(blue)
  );
  const perceptual = linear <= 0.0031308
    ? 12.92 * linear
    : 1.055 * (linear ** (1 / 2.4)) - 0.055;
  return clampByte(perceptual * 255);
}


function assertRgba(source) {
  if (!(source instanceof Uint8ClampedArray) || source.length % 4 !== 0) {
    throw new CompositorError('Expected an RGBA Uint8ClampedArray');
  }
}


export function tintRgba(source, maskAlpha, lut, toneMap) {
  assertRgba(source);
  const pixels = source.length / 4;
  if (maskAlpha.length !== pixels || lut.length !== 768 || toneMap.length !== 256) {
    throw new CompositorError('Hair tint inputs have incompatible lengths');
  }
  const output = new Uint8ClampedArray(source);
  for (let pixel = 0; pixel < pixels; pixel += 1) {
    const offset = pixel * 4;
    if (maskAlpha[pixel] === 0 || source[offset + 3] === 0) continue;
    const luminance = luminanceIndex(source[offset], source[offset + 1], source[offset + 2]);
    const target = toneMap[luminance] * 3;
    output[offset] = lut[target];
    output[offset + 1] = lut[target + 1];
    output[offset + 2] = lut[target + 2];
  }
  return output;
}


function assertImage(image, width = null, height = null) {
  if (!image || !Number.isInteger(image.width) || !Number.isInteger(image.height)) {
    throw new CompositorError('Decoded asset is not image data');
  }
  assertRgba(image.data);
  if (image.data.length !== image.width * image.height * 4) {
    throw new CompositorError('Decoded asset dimensions do not match its pixels');
  }
  if ((width !== null && image.width !== width) || (height !== null && image.height !== height)) {
    throw new CompositorError('Layer canvas dimensions do not match');
  }
}


function alphaCompositeInto(destination, source) {
  for (let offset = 0; offset < destination.length; offset += 4) {
    const sourceAlphaByte = source[offset + 3];
    if (sourceAlphaByte === 0) continue;
    if (sourceAlphaByte === 255 || destination[offset + 3] === 0) {
      destination[offset] = source[offset];
      destination[offset + 1] = source[offset + 1];
      destination[offset + 2] = source[offset + 2];
      destination[offset + 3] = sourceAlphaByte;
      continue;
    }
    const sourceAlpha = sourceAlphaByte / 255;
    const destinationAlpha = destination[offset + 3] / 255;
    const outputAlpha = sourceAlpha + destinationAlpha * (1 - sourceAlpha);
    for (let channel = 0; channel < 3; channel += 1) {
      destination[offset + channel] = (
        source[offset + channel] * sourceAlpha
        + destination[offset + channel] * destinationAlpha * (1 - sourceAlpha)
      ) / outputAlpha;
    }
    destination[offset + 3] = outputAlpha * 255;
  }
}


function extractAlpha(image) {
  const alpha = new Uint8ClampedArray(image.width * image.height);
  for (let pixel = 0; pixel < alpha.length; pixel += 1) alpha[pixel] = image.data[pixel * 4 + 3];
  return alpha;
}


function buildHairToneMap(images, maskAlpha) {
  if (images.length === 0) throw new CompositorError('No hair owner layers were supplied');
  const combined = new Uint8ClampedArray(images[0].data.length);
  for (const image of images) alphaCompositeInto(combined, image.data);
  const histogram = new Float64Array(256);
  let strictProfileCount = 0;
  for (let pixel = 0; pixel < maskAlpha.length; pixel += 1) {
    const offset = pixel * 4;
    if (maskAlpha[pixel] > 0 && combined[offset + 3] >= 128) {
      histogram[luminanceIndex(combined[offset], combined[offset + 1], combined[offset + 2])] += 1;
      strictProfileCount += 1;
    }
  }
  if (strictProfileCount === 0) {
    for (let pixel = 0; pixel < maskAlpha.length; pixel += 1) {
      const offset = pixel * 4;
      if (maskAlpha[pixel] > 0 && combined[offset + 3] > 0) {
        histogram[luminanceIndex(combined[offset], combined[offset + 1], combined[offset + 2])] += 1;
      }
    }
  }
  const occupied = [];
  let cumulative = 0;
  const midpoints = new Float64Array(256);
  for (let index = 0; index < 256; index += 1) {
    if (histogram[index] > 0) occupied.push(index);
    cumulative += histogram[index];
    midpoints[index] = cumulative - histogram[index] * 0.5;
  }
  if (occupied.length < 2) throw new CompositorError('Hair sources lack a usable luminance range');
  const first = midpoints[occupied[0]];
  const last = midpoints[occupied.at(-1)];
  const normalized = new Map(occupied.map((index) => [
    index,
    (midpoints[index] - first) * (255 / (last - first)),
  ]));
  const toneMap = new Uint8ClampedArray(256);
  let segment = 0;
  for (let index = 0; index < 256; index += 1) {
    if (index <= occupied[0]) {
      toneMap[index] = 0;
      continue;
    }
    if (index >= occupied.at(-1)) {
      toneMap[index] = 255;
      continue;
    }
    while (occupied[segment + 1] < index) segment += 1;
    const left = occupied[segment];
    const right = occupied[segment + 1];
    const weight = (index - left) / (right - left);
    toneMap[index] = normalized.get(left) * (1 - weight) + normalized.get(right) * weight;
  }
  return toneMap;
}


export function composeFrame(selection, bindings, sources) {
  if (!Array.isArray(bindings) || bindings.length === 0) {
    throw new CompositorError('A portrait requires at least one layer binding');
  }
  const first = sources.get(bindings[0].path);
  assertImage(first);
  const { width, height } = first;
  for (const binding of bindings) assertImage(sources.get(binding.path), width, height);

  const hairBindings = bindings.filter(({ tintMask }) => tintMask);
  const tinted = new Map();
  if (hairBindings.length > 0) {
    const maskPaths = new Set(hairBindings.map(({ tintMask }) => tintMask.path));
    if (maskPaths.size !== 1) throw new CompositorError('Hair layers do not share one tint mask');
    const mask = sources.get([...maskPaths][0]);
    assertImage(mask, width, height);
    const maskAlpha = extractAlpha(mask);
    const hairImages = hairBindings.map(({ path }) => sources.get(path));
    const toneMap = buildHairToneMap(hairImages, maskAlpha);
    const lut = buildLuminanceLut(deriveHairPalette(selection.hairHue));
    for (const binding of hairBindings) {
      const source = sources.get(binding.path);
      tinted.set(binding.path, tintRgba(source.data, maskAlpha, lut, toneMap));
    }
  }

  const result = new Uint8ClampedArray(width * height * 4);
  let faceCheckpoint = null;
  for (const binding of [...bindings].sort((left, right) => left.order - right.order)) {
    const sourceImage = sources.get(binding.path);
    const source = tinted.get(binding.path) ?? sourceImage.data;
    if (binding.operation === 'ownership-reset') {
      if (!faceCheckpoint) throw new CompositorError('Ownership reset occurs before face checkpoint');
      for (let pixel = 0; pixel < width * height; pixel += 1) {
        const offset = pixel * 4;
        if (sourceImage.data[offset + 3] === 0) continue;
        result.set(faceCheckpoint.subarray(offset, offset + 4), offset);
      }
      continue;
    }
    alphaCompositeInto(result, source);
    if (FACE_BASE_ROLES.has(binding.role)) faceCheckpoint = new Uint8ClampedArray(result);
  }
  return Object.freeze({ width, height, data: result });
}


export class BrowserImageLoader {
  #cache = new Map();

  constructor({
    fetchImpl = globalThis.fetch?.bind(globalThis),
    bitmapFactory = globalThis.createImageBitmap?.bind(globalThis),
    canvasFactory = () => document.createElement('canvas'),
    maxEntries = 32,
  } = {}) {
    if (!fetchImpl || !bitmapFactory) throw new CompositorError('Browser image APIs are unavailable');
    if (!Number.isInteger(maxEntries) || maxEntries < 1) {
      throw new CompositorError('Image cache size must be a positive integer');
    }
    this.fetchImpl = fetchImpl;
    this.bitmapFactory = bitmapFactory;
    this.canvasFactory = canvasFactory;
    this.maxEntries = maxEntries;
  }

  load(path) {
    if (!/^assets\/[A-Za-z0-9_./-]+$/.test(path) || path.includes('..')) {
      return Promise.reject(new CompositorError(`Unsafe asset URL: ${path}`));
    }
    if (this.#cache.has(path)) {
      const cached = this.#cache.get(path);
      this.#cache.delete(path);
      this.#cache.set(path, cached);
      return cached;
    }
    let promise = this.#decode(path);
    promise = promise.catch((error) => {
      if (this.#cache.get(path) === promise) this.#cache.delete(path);
      throw error;
    });
    this.#cache.set(path, promise);
    if (this.#cache.size > this.maxEntries) {
      this.#cache.delete(this.#cache.keys().next().value);
    }
    return promise;
  }

  async #decode(path) {
    const response = await this.fetchImpl(`./${path}`, { credentials: 'same-origin' });
    if (!response.ok) throw new CompositorError(`Could not load ${path}: HTTP ${response.status}`);
    const bitmap = await this.bitmapFactory(await response.blob());
    try {
      if (bitmap.width !== 1254 || bitmap.height !== 1254) {
        throw new CompositorError(`Asset canvas drift: ${path}: ${bitmap.width}×${bitmap.height}`);
      }
      const canvas = this.canvasFactory();
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) throw new CompositorError('Canvas 2D context is unavailable');
      context.drawImage(bitmap, 0, 0);
      const pixels = context.getImageData(0, 0, bitmap.width, bitmap.height);
      return Object.freeze({
        width: bitmap.width,
        height: bitmap.height,
        data: new Uint8ClampedArray(pixels.data),
      });
    } finally {
      bitmap.close?.();
    }
  }
}


export class PortraitCompositor {
  #version = 0;
  #committedRecipe = null;

  constructor({ outputCanvas, imageLoader = null, frameComposer = composeFrame } = {}) {
    if (!outputCanvas?.getContext) throw new CompositorError('An output canvas is required');
    this.outputCanvas = outputCanvas;
    this.outputContext = outputCanvas.getContext('2d');
    if (!this.outputContext) throw new CompositorError('Canvas 2D context is unavailable');
    this.imageLoader = imageLoader ?? new BrowserImageLoader();
    this.frameComposer = frameComposer;
  }

  get committedRecipe() {
    return this.#committedRecipe;
  }

  async render(selection, bindings, signal = null) {
    const version = ++this.#version;
    const paths = new Set();
    for (const binding of bindings) {
      paths.add(binding.path);
      if (binding.tintMask) paths.add(binding.tintMask.path);
    }
    const decoded = await Promise.all(
      [...paths].map(async (path) => [path, await this.imageLoader.load(path)]),
    );
    if (version !== this.#version || signal?.aborted) return { committed: false };
    const frame = await this.frameComposer(selection, bindings, new Map(decoded));
    if (version !== this.#version || signal?.aborted) return { committed: false };
    const imageData = typeof ImageData === 'undefined'
      ? frame
      : new ImageData(frame.data, frame.width, frame.height);
    this.outputContext.putImageData(imageData, 0, 0);
    this.#committedRecipe = selection.recipe ?? null;
    return { committed: true, recipe: this.#committedRecipe };
  }

  toPngBlob() {
    return new Promise((resolve, reject) => {
      this.outputCanvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new CompositorError('Canvas PNG export returned no data'));
      }, 'image/png');
    });
  }
}
