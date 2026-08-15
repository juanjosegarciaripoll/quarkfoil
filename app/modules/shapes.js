const SVG_NS = "http://www.w3.org/2000/svg";

function svgElement(name, attributes) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

const SHAPE_DEFINITIONS = Object.freeze({
  rectangle: { label: "Rectangle", initialGeometry: { x: 41, y: 29, w: 18, h: 32 }, labelInsets: [0, 0, 0, 0], draw: common => svgElement("rect", { ...common, x: "0", y: "0", width: "100", height: "100" }) },
  "rounded-rectangle": { label: "Rounded rectangle", labelInsets: [5, 5, 5, 5], draw: common => svgElement("rect", { ...common, x: "0", y: "0", width: "100", height: "100", rx: "11", ry: "11" }) },
  ellipse: { label: "Ellipse", labelInsets: [15, 15, 15, 15], draw: common => svgElement("ellipse", { ...common, cx: "50", cy: "50", rx: "50", ry: "50" }) },
  circle: { label: "Circle", labelInsets: [15, 15, 15, 15], draw: common => svgElement("circle", { ...common, cx: "50", cy: "50", r: "50" }) },
  diamond: { label: "Diamond", labelInsets: [25, 25, 25, 25], draw: common => svgElement("polygon", { ...common, points: "50,0 100,50 50,100 0,50" }) },
  hexagon: { label: "Hexagon", labelInsets: [8, 20, 8, 20], draw: common => svgElement("polygon", { ...common, points: "25,0 75,0 100,50 75,100 25,100 0,50" }) },
  cross: { label: "Cross", initialGeometry: { x: 41, y: 29, w: 18, h: 32 }, labelInsets: [36, 36, 36, 36], draw: common => svgElement("polygon", { ...common, points: "35,0 65,0 65,35 100,35 100,65 65,65 65,100 35,100 35,65 0,65 0,35 35,35" }) },
  x: { label: "X", labelInsets: [36, 36, 36, 36], draw: common => svgElement("polygon", { ...common, points: "0,20 20,0 50,30 80,0 100,20 70,50 100,80 80,100 50,70 20,100 0,80 30,50" }) },
  star: { label: "Five-pointed star", initialGeometry: { x: 41, y: 29, w: 18, h: 32 }, labelInsets: [38, 38, 42, 38], draw: common => svgElement("polygon", { ...common, points: "50,0 61.8,33.8 97.6,34.5 68.6,55.7 79.4,90.5 50,70 20.6,90.5 31.4,55.7 2.4,34.5 38.2,33.8" }) },
  cloud: { label: "Cloud", labelInsets: [15, 12, 10, 12], draw: common => svgElement("path", { ...common, d: "M20 100 C7 100 0 88 5 73 C0 58 7 40 20 39 C22 20 39 10 52 20 C65 5 86 15 87 34 C100 38 100 57 96 70 C100 86 89 100 75 100 Z" }) },
  callout: { label: "Comic callout", labelInsets: [0, 0, 22, 0], draw: common => svgElement("path", { ...common, d: "M10 0 H90 Q100 0 100 10 V68 Q100 78 90 78 H37 L15 100 L20 78 H10 Q0 78 0 68 V10 Q0 0 10 0 Z" }) },
});

export const SHAPES = Object.freeze(Object.fromEntries(
  Object.entries(SHAPE_DEFINITIONS).map(([name, definition]) => [name, definition.label]),
));

export function shapeLabelInsets(shape) {
  const name = Object.hasOwn(SHAPE_DEFINITIONS, shape) ? shape : "rectangle";
  return SHAPE_DEFINITIONS[name].labelInsets;
}

export function initialShapeGeometry(shape) {
  const name = Object.hasOwn(SHAPE_DEFINITIONS, shape) ? shape : "rectangle";
  return { ...(SHAPE_DEFINITIONS[name].initialGeometry || { x: 35, y: 35, w: 30, h: 20 }) };
}

export function makeShapeSvg(shape) {
  const name = Object.hasOwn(SHAPES, shape) ? shape : "rectangle";
  const svg = svgElement("svg", {
    class: "shape-background",
    viewBox: "0 0 100 100",
    preserveAspectRatio: name === "circle" ? "xMidYMid meet" : "none",
    "aria-hidden": "true",
  });
  const common = { class: "shape-surface", "vector-effect": "non-scaling-stroke" };
  svg.append(SHAPE_DEFINITIONS[name].draw(common));
  return svg;
}
