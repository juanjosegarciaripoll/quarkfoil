const FUNCTIONS = Object.freeze({
  abs: Math.abs, acos: Math.acos, asin: Math.asin, atan: Math.atan, atan2: Math.atan2,
  ceil: Math.ceil, cos: Math.cos, exp: Math.exp, floor: Math.floor, log: Math.log,
  log10: Math.log10, max: Math.max, min: Math.min, pow: Math.pow, round: Math.round,
  sign: Math.sign, sin: Math.sin, sqrt: Math.sqrt, tan: Math.tan,
});

function tokenize(source) {
  const tokens = [];
  let offset = 0;
  while (offset < source.length) {
    const rest = source.slice(offset);
    const whitespace = /^\s+/.exec(rest);
    if (whitespace) { offset += whitespace[0].length; continue; }
    const number = /^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?/i.exec(rest);
    if (number) { tokens.push({ type: "number", value: Number(number[0]) }); offset += number[0].length; continue; }
    const identifier = /^(?:Math\.)?[A-Za-z_$][\w$]*/.exec(rest);
    if (identifier) { tokens.push({ type: "identifier", value: identifier[0].replace(/^Math\./, "") }); offset += identifier[0].length; continue; }
    const operator = /^(?:\*\*|[+\-*/%(),])/.exec(rest);
    if (operator) { tokens.push({ type: operator[0], value: operator[0] }); offset += operator[0].length; continue; }
    throw new Error(`Unexpected '${rest[0]}' at position ${offset + 1}`);
  }
  tokens.push({ type: "end" });
  return tokens;
}

export function compileExpression(source) {
  const tokens = tokenize(source);
  let index = 0;
  const peek = type => tokens[index].type === type;
  const take = type => {
    if (!peek(type)) throw new Error(`Expected '${type}'`);
    return tokens[index++];
  };
  const primary = () => {
    if (peek("number")) { const value = take("number").value; return () => value; }
    if (peek("(")) { take("("); const value = expression(); take(")"); return value; }
    if (!peek("identifier")) throw new Error("Expected a number, x, t, or function");
    const name = take("identifier").value;
    if (["x", "t"].includes(name)) return x => x;
    if (["PI", "E"].includes(name) && !peek("(")) { const value = Math[name]; return () => value; }
    const fn = FUNCTIONS[name];
    if (!fn) throw new Error(`Unknown function or value '${name}'`);
    take("(");
    const args = [];
    if (!peek(")")) {
      args.push(expression());
      while (peek(",")) { take(","); args.push(expression()); }
    }
    take(")");
    return x => fn(...args.map(arg => arg(x)));
  };
  const unary = () => {
    if (peek("+")) { take("+"); return unary(); }
    if (peek("-")) { take("-"); const value = unary(); return x => -value(x); }
    return primary();
  };
  const power = () => {
    const left = unary();
    if (!peek("**")) return left;
    take("**"); const right = power(); return x => left(x) ** right(x);
  };
  const multiply = () => {
    let left = power();
    while (["*", "/", "%"].includes(tokens[index].type)) {
      const operator = tokens[index++].type; const right = power(); const previous = left;
      left = operator === "*" ? x => previous(x) * right(x) : operator === "/" ? x => previous(x) / right(x) : x => previous(x) % right(x);
    }
    return left;
  };
  const expression = () => {
    let left = multiply();
    while (["+", "-"].includes(tokens[index].type)) {
      const operator = tokens[index++].type; const right = multiply(); const previous = left;
      left = operator === "+" ? x => previous(x) + right(x) : x => previous(x) - right(x);
    }
    return left;
  };
  const evaluate = expression();
  if (!peek("end")) throw new Error(`Unexpected '${tokens[index].value}'`);
  return evaluate;
}

function cubicValue(start, control1, control2, end, time) {
  const inverse = 1 - time;
  return inverse ** 3 * start + 3 * inverse ** 2 * time * control1 + 3 * inverse * time ** 2 * control2 + time ** 3 * end;
}

function cubicRange(start, control1, control2, end) {
  const values = [start, end];
  const a = -start + 3 * control1 - 3 * control2 + end;
  const b = 2 * (start - 2 * control1 + control2);
  const c = control1 - start;
  const roots = [];
  if (Math.abs(a) < 1e-12) {
    if (Math.abs(b) >= 1e-12) roots.push(-c / b);
  } else {
    const discriminant = b * b - 4 * a * c;
    if (discriminant >= 0) {
      roots.push((-b + Math.sqrt(discriminant)) / (2 * a), (-b - Math.sqrt(discriminant)) / (2 * a));
    }
  }
  for (const time of roots) if (time > 0 && time < 1) values.push(cubicValue(start, control1, control2, end, time));
  return [Math.min(...values), Math.max(...values)];
}

function splineGeometry(points) {
  if (points.length < 2) return null;
  let path = `M${points[0][0].toFixed(2)} ${points[0][1].toFixed(2)}`;
  const bounds = { minimumX: points[0][0], maximumX: points[0][0], minimumY: points[0][1], maximumY: points[0][1] };
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[Math.max(0, index - 1)];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[Math.min(points.length - 1, index + 2)];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    path += ` C${c1[0].toFixed(2)} ${c1[1].toFixed(2)} ${c2[0].toFixed(2)} ${c2[1].toFixed(2)} ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`;
    const [minimumX, maximumX] = cubicRange(p1[0], c1[0], c2[0], p2[0]);
    const [minimumY, maximumY] = cubicRange(p1[1], c1[1], c2[1], p2[1]);
    bounds.minimumX = Math.min(bounds.minimumX, minimumX);
    bounds.maximumX = Math.max(bounds.maximumX, maximumX);
    bounds.minimumY = Math.min(bounds.minimumY, minimumY);
    bounds.maximumY = Math.max(bounds.maximumY, maximumY);
  }
  return { path, bounds, first: points[0], last: points.at(-1) };
}

export function createPlotSvg(expression, start, end, pointCount, axes, yExpression = "") {
  if (!Number.isFinite(start) || !Number.isFinite(end) || start === end) throw new Error("Start and end must be different finite numbers");
  const parametric = Boolean(String(yExpression).trim());
  const evaluateX = parametric ? compileExpression(expression) : value => value;
  const evaluateY = compileExpression(parametric ? yExpression : expression);
  const samples = Array.from({ length: pointCount }, (_, index) => {
    const parameter = start + (end - start) * index / (pointCount - 1);
    return { x: Number(evaluateX(parameter)), y: Number(evaluateY(parameter)) };
  });
  const finite = samples.filter(point => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (finite.length < 2) throw new Error(`${parametric ? "The expressions produce" : "The expression produces"} fewer than two finite points`);
  let coordinateMinimumX = parametric ? Math.min(...finite.map(point => point.x)) : Math.min(start, end);
  let coordinateMaximumX = parametric ? Math.max(...finite.map(point => point.x)) : Math.max(start, end);
  let minimumY = Math.min(...finite.map(point => point.y));
  let maximumY = Math.max(...finite.map(point => point.y));
  if (coordinateMinimumX === coordinateMaximumX) { coordinateMinimumX -= 0.5; coordinateMaximumX += 0.5; }
  if (minimumY === maximumY) { minimumY -= 0.5; maximumY += 0.5; }
  const width = 800, height = 450;
  const padding = axes ? { left: 58, right: 22, top: 22, bottom: 42 } : { left: 0, right: 0, top: 0, bottom: 0 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const horizontalStart = parametric ? coordinateMinimumX : start;
  const horizontalEnd = parametric ? coordinateMaximumX : end;
  const scale = point => [
    padding.left + (point.x - horizontalStart) / (horizontalEnd - horizontalStart) * plotWidth,
    padding.top + (maximumY - point.y) / (maximumY - minimumY) * plotHeight,
  ];
  const segments = [];
  let segment = [];
  for (const point of samples) {
    if (Number.isFinite(point.x) && Number.isFinite(point.y)) segment.push(scale(point));
    else if (segment.length) { segments.push(segment); segment = []; }
  }
  if (segment.length) segments.push(segment);
  const geometries = segments.map(splineGeometry).filter(Boolean);
  const paths = geometries.map(item => `<path d="${item.path}"/>`).join("");
  const baselineY = padding.top + (maximumY - Math.max(minimumY, Math.min(maximumY, 0))) / (maximumY - minimumY) * plotHeight;
  const areas = geometries.map(item => `<path d="${item.path} L${item.last[0].toFixed(2)} ${baselineY.toFixed(2)} L${item.first[0].toFixed(2)} ${baselineY.toFixed(2)} Z"/>`).join("");
  let axisMarkup = "";
  if (axes) {
    const yAxisX = padding.left + (Math.max(Math.min(horizontalStart, horizontalEnd), Math.min(Math.max(horizontalStart, horizontalEnd), 0)) - horizontalStart) / (horizontalEnd - horizontalStart) * plotWidth;
    axisMarkup = `<g class="axes" fill="none" stroke="#61717b" stroke-width="1.5"><path d="M${padding.left} ${baselineY.toFixed(2)}H${width - padding.right}"/><path d="M${yAxisX.toFixed(2)} ${padding.top}V${height - padding.bottom}"/></g>`;
  }
  const strokeAllowance = 1.5;
  const plotMinimumX = Math.min(0, ...geometries.map(item => item.bounds.minimumX));
  const plotMaximumX = Math.max(width, ...geometries.map(item => item.bounds.maximumX));
  const plotMinimumY = Math.min(0, ...geometries.map(item => item.bounds.minimumY));
  const plotMaximumY = Math.max(height, ...geometries.map(item => item.bounds.maximumY));
  const minimumX = plotMinimumX - strokeAllowance;
  const maximumX = plotMaximumX + strokeAllowance;
  const minimumViewY = plotMinimumY - strokeAllowance;
  const maximumViewY = plotMaximumY + strokeAllowance;
  const viewBox = `${minimumX.toFixed(2)} ${minimumViewY.toFixed(2)} ${(maximumX - minimumX).toFixed(2)} ${(maximumViewY - minimumViewY).toFixed(2)}`;
  const bounds = `${plotMinimumX.toFixed(4)} ${plotMinimumY.toFixed(4)} ${(plotMaximumX - plotMinimumX).toFixed(4)} ${(plotMaximumY - plotMinimumY).toFixed(4)}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" data-quarkfoil-plot="1" data-plot-kind="${parametric ? "parametric" : "function"}" data-plot-bounds="${bounds}" data-area-baseline="${baselineY.toFixed(2)}"><rect class="plot-background" x="${minimumX.toFixed(2)}" y="${minimumViewY.toFixed(2)}" width="${(maximumX - minimumX).toFixed(2)}" height="${(maximumViewY - minimumViewY).toFixed(2)}" fill="none"/><g class="area" fill="none" stroke="none">${areas}</g>${axisMarkup}<g class="curve" fill="none" stroke="#146c7e" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">${paths}</g></svg>`;
}
