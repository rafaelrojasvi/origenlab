import { useEffect, useRef } from "react";
import { HEADER_CANVAS_PX } from "../../lib/logo/composition";
import { startThreeBodyCanvas } from "../../lib/logo/threeBodyCanvasRunner";

/** Logo animado para la barra superior únicamente. */
export function OrigenLabAnimatedLogo() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const displayPx = 32;
  const canvasPx = HEADER_CANVAS_PX;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    return startThreeBodyCanvas(canvas, { loopSeconds: 18, showRings: true });
  }, []);

  return (
    <div className="flex items-center gap-2" data-testid="origenlab-logo-animated">
      <div
        className="relative shrink-0 motion-reduce:hidden"
        style={{ width: displayPx, height: displayPx }}
      >
        <canvas
          ref={canvasRef}
          className="block"
          style={{ width: displayPx, height: displayPx }}
          width={canvasPx}
          height={canvasPx}
          aria-hidden
        />
      </div>
      <img
        src="/logo/origenlab-mark-static.svg"
        alt=""
        className="hidden h-8 w-8 shrink-0 motion-reduce:block"
        aria-hidden
      />
      <span className="text-sm font-semibold text-brand-950">OrigenLab</span>
    </div>
  );
}
