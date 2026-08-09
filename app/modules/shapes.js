const SVG_NS = "http://www.w3.org/2000/svg";

export const SHAPES = Object.freeze({
  rectangle: "Rectangle",
  "rounded-rectangle": "Rounded rectangle",
  ellipse: "Ellipse",
  circle: "Circle",
  diamond: "Diamond",
  hexagon: "Hexagon",
  cloud: "Cloud",
  callout: "Comic callout",
  sine: "Sine curve (0–2π)",
  cosine: "Cosine curve (0–2π)",
});

function svgElement(name, attributes) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
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
  const curve = functionName => {
    const points = Array.from({ length: 65 }, (_, index) => {
      const phase = 2 * Math.PI * index / 64;
      const x = 5 + 90 * index / 64;
      const y = 50 - 38 * Math[functionName](phase);
      return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    const group = svgElement("g", {});
    group.append(
      svgElement("rect", { ...common, x: "2", y: "2", width: "96", height: "96" }),
      svgElement("path", { class: "shape-axis", d: "M5 50 H95 M5 12 V88", "vector-effect": "non-scaling-stroke" }),
      svgElement("path", { class: "shape-curve", d: points, "vector-effect": "non-scaling-stroke" }),
    );
    return group;
  };
  const elements = {
    rectangle: () => svgElement("rect", { ...common, x: "2", y: "2", width: "96", height: "96" }),
    "rounded-rectangle": () => svgElement("rect", { ...common, x: "2", y: "2", width: "96", height: "96", rx: "11", ry: "11" }),
    ellipse: () => svgElement("ellipse", { ...common, cx: "50", cy: "50", rx: "48", ry: "48" }),
    circle: () => svgElement("circle", { ...common, cx: "50", cy: "50", r: "48" }),
    diamond: () => svgElement("polygon", { ...common, points: "50,2 98,50 50,98 2,50" }),
    hexagon: () => svgElement("polygon", { ...common, points: "25,2 75,2 98,50 75,98 25,98 2,50" }),
    cloud: () => svgElement("path", { ...common, d: "M22 82 C10 82 3 72 7 61 C1 50 8 37 21 36 C23 21 39 13 52 21 C64 9 84 17 85 33 C98 37 102 53 94 63 C98 75 88 84 76 82 Z" }),
    callout: () => svgElement("path", { ...common, d: "M13 5 H87 Q97 5 97 15 V68 Q97 78 87 78 H37 L17 96 L22 78 H13 Q3 78 3 68 V15 Q3 5 13 5 Z" }),
    sine: () => curve("sin"),
    cosine: () => curve("cos"),
  };
  svg.append(elements[name]());
  return svg;
}
