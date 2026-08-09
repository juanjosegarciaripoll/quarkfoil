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
      const x = 100 * index / 64;
      const y = 50 - 38 * Math[functionName](phase);
      return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    const group = svgElement("g", {});
    group.append(
      svgElement("rect", { ...common, x: "0", y: "0", width: "100", height: "100" }),
      svgElement("path", { class: "shape-axis", d: "M0 50 H100 M0 12 V88", "vector-effect": "non-scaling-stroke" }),
      svgElement("path", { class: "shape-curve", d: points, "vector-effect": "non-scaling-stroke" }),
    );
    return group;
  };
  const elements = {
    rectangle: () => svgElement("rect", { ...common, x: "0", y: "0", width: "100", height: "100" }),
    "rounded-rectangle": () => svgElement("rect", { ...common, x: "0", y: "0", width: "100", height: "100", rx: "11", ry: "11" }),
    ellipse: () => svgElement("ellipse", { ...common, cx: "50", cy: "50", rx: "50", ry: "50" }),
    circle: () => svgElement("circle", { ...common, cx: "50", cy: "50", r: "50" }),
    diamond: () => svgElement("polygon", { ...common, points: "50,0 100,50 50,100 0,50" }),
    hexagon: () => svgElement("polygon", { ...common, points: "25,0 75,0 100,50 75,100 25,100 0,50" }),
    cloud: () => svgElement("path", { ...common, d: "M20 100 C7 100 0 88 5 73 C0 58 7 40 20 39 C22 20 39 10 52 20 C65 5 86 15 87 34 C100 38 100 57 96 70 C100 86 89 100 75 100 Z" }),
    callout: () => svgElement("path", { ...common, d: "M10 0 H90 Q100 0 100 10 V68 Q100 78 90 78 H37 L15 100 L20 78 H10 Q0 78 0 68 V10 Q0 0 10 0 Z" }),
    sine: () => curve("sin"),
    cosine: () => curve("cos"),
  };
  svg.append(elements[name]());
  return svg;
}
