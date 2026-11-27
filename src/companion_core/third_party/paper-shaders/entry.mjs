import { ShaderMount, defaultObjectSizing, ShaderFitOptions, LiquidMetalShapes,
  liquidMetalFragmentShader, getShaderColorFromString } from './package/dist/index.js';

export function createMaterial(element, frame) {
  const d = defaultObjectSizing;
  return new ShaderMount(element, liquidMetalFragmentShader, {
    u_fit: ShaderFitOptions.contain,
    u_scale: 0.94,
    u_rotation: 10,
    u_originX: d.originX, u_originY: d.originY,
    u_offsetX: d.offsetX, u_offsetY: d.offsetY, u_worldWidth: d.worldWidth, u_worldHeight: d.worldHeight,
    u_colorBack: getShaderColorFromString('#162222'),
    u_colorTint: getShaderColorFromString('#d6ffef'),
    u_isImage: false, u_shape: LiquidMetalShapes.diamond,
    u_repetition: 1.8, u_softness: 0.17, u_shiftRed: 0.05, u_shiftBlue: 0.15,
    u_distortion: 0.09, u_contour: 0.38, u_angle: 69
  }, undefined, 0.34, frame, 1, 262144);
}

