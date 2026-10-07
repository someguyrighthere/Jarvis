const clamp = value => Math.max(0, Math.min(1, value));
export const ease = value => {
  const t = clamp(value);
  return clamp(t * t * t * (10 + t * (-15 + t * 6)));
};

export function dampMotion(current, target, delta, tracking) {
  const blend = 1 - Math.exp(-(tracking ? 16 : 3.5) * delta);
  for (const key of ['lift', 'travel', 'accent', 'wrist', 'fingers']) {
    current[key] += (target[key] - current[key]) * blend;
  }
  if (target.lift > 0) current.variant = target.variant;
  return current;
}

export function speakingSway(time, blend) {
  return {
    lateral: blend * (Math.sin(time * 0.72) * 0.024 + Math.sin(time * 0.31 + 0.8) * 0.007),
    forward: blend * Math.sin(time * 0.49 + 0.4) * 0.008,
  };
}

export function stanceMotion(time, blend, stepSeconds = -1, side = 1) {
  const shifting = Math.sin(time * Math.PI / 11);
  let placement = 0;
  let lift = 0;
  if (stepSeconds >= 0 && stepSeconds < 8) {
    if (stepSeconds < 1.2) {
      placement = ease(stepSeconds / 1.2);
      lift = Math.sin(Math.PI * stepSeconds / 1.2) ** 2 * 0.025;
    } else if (stepSeconds < 6.8) {
      placement = 1;
    } else {
      placement = 1 - ease((stepSeconds - 6.8) / 1.2);
      lift = Math.sin(Math.PI * (stepSeconds - 6.8) / 1.2) ** 2 * 0.025;
    }
  }
  const support = ease(stepSeconds / 0.5) * (1 - ease((stepSeconds - 7.5) / 0.5));
  return {
    hipX: blend * (shifting * 0.022 * (1 - support) - side * support * 0.025),
    hipY: -blend * (0.004 + Math.abs(shifting) * 0.001),
    hipRoll: blend * shifting * 0.008 * (1 - support),
    footX: side * placement * 0.035,
    footZ: placement * 0.018,
    footLift: lift,
    footYaw: side * placement * 0.07,
  };
}

export function gestureMotion(event, seconds) {
  const t = seconds - event.start;
  const prepare = event.prepare ?? event.duration * 0.28;
  const stroke = event.stroke ?? event.duration * 0.24;
  const hold = event.hold ?? event.duration * 0.1;
  const recover = event.recover ?? event.duration - prepare - stroke - hold;
  if (t < 0 || t >= event.duration) {
    const carry = t >= event.duration && seconds < (event.link_next ?? 0) ? 0.28 : 0;
    return { lift: carry, travel: 0, accent: 0 };
  }
  const carryIn = event.linked ? 0.28 : 0;
  const carryOut = event.link_next != null ? 0.28 : 0;
  const recovery = ease((t - prepare - stroke - hold) / recover);
  const lift = (carryIn + (1 - carryIn) * ease(t / prepare)) * (1 - (1 - carryOut) * recovery);
  const travel = ease((t - prepare) / stroke) * (1 - (carryOut ? recovery : 0));
  const strokePhase = clamp((t - prepare) / stroke);
  const accent = Math.sin(Math.PI * strokePhase) ** 2;
  return { lift, travel, accent };
}

export const speechPaths = {
  greeting: { ready: [0.23, 0.34, 0.16], end: [0.28, 0.38, 0.2], palm: [0, 0, 1] },
  explanation: { ready: [0.18, 0.18, 0.2], end: [0.27, 0.22, 0.25], palm: [0, 1, 0] },
  emphasis: { ready: [0.18, 0.28, 0.22], end: [0.19, 0.21, 0.25], palm: [0, 0, -1] },
  uncertainty: { ready: [0.2, 0.19, 0.2], end: [0.28, 0.23, 0.24], palm: [0, 1, 0] },
  beat: { ready: [0.17, 0.17, 0.18], end: [0.19, 0.13, 0.21], palm: [0, 0, -1] },
};
