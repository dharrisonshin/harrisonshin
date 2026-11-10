(function(){
  const canvas = document.getElementById('sky');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  function mulberry32(a){
    return function(){
      a |= 0; a = a + 0x6D2B79F5 | 0;
      let t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  let stars = [];
  function build(){
    const W = innerWidth, H = innerHeight;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    stars = [];
    const n = Math.floor(W * H / 3200);
    const r = mulberry32(0xA11CE);
    for (let i = 0; i < n; i++){
      const bright = r() > 0.92;
      stars.push({
        x: r() * W,
        y: r() * H,
        rad: bright ? 0.9 + r() * 0.7 : 0.3 + r() * 0.55,
        a: bright ? 0.22 + r() * 0.16 : 0.08 + r() * 0.14,
        gold: r() < 0.07
      });
    }
    ctx.clearRect(0, 0, W, H);
    for (let i = 0; i < stars.length; i++){
      const s = stars[i];
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.rad, 0, Math.PI * 2);
      ctx.fillStyle = s.gold ? 'rgba(217,180,90,' + s.a + ')' : 'rgba(255,255,255,' + s.a + ')';
      ctx.fill();
    }
  }
  addEventListener('resize', build);
  build();
})();
