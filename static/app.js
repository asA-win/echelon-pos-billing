const fmt=n=>'₹'+Number(n||0).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
let cart=[];
function addItem(id,name,sku,price,stock){
 const found=cart.find(x=>x.id===id);
 if(found){if(found.qty>=stock){toast('Only '+stock+' units available.');return;}found.qty++;}
 else cart.push({id,name,sku,price:Number(price),stock:Number(stock),qty:1});
 renderCart();
}
function changeQty(id,delta){const x=cart.find(i=>i.id===id);if(!x)return;x.qty+=delta;if(x.qty<=0)cart=cart.filter(i=>i.id!==id);else if(x.qty>x.stock){x.qty=x.stock;toast('Maximum stock reached.');}renderCart();}
function clearCart(){cart=[];renderCart();}
function renderCart(){
 const el=document.getElementById('cartItems');if(!el)return;
 document.getElementById('cartCount').textContent=cart.reduce((a,x)=>a+x.qty,0);
 if(!cart.length){el.innerHTML='<div class="empty-cart"><span>▤</span><b>Your bill is empty</b><p>Add products to get started.</p></div>';}
 else el.innerHTML=cart.map(x=>`<div class="cart-item"><div class="product-thumb">${x.name.slice(0,1)}</div><div class="cart-item-info"><b>${escapeHtml(x.name)}</b><small>${x.sku} · ${fmt(x.price)}</small><div class="qty-control"><button onclick="changeQty(${x.id},-1)">−</button><b>${x.qty}</b><button onclick="changeQty(${x.id},1)">+</button></div></div><div class="cart-line-total"><b>${fmt(x.price*x.qty)}</b><button class="remove-item" onclick="changeQty(${x.id},-${x.qty})">×</button></div></div>`).join('');
 const sub=cart.reduce((a,x)=>a+x.qty*x.price,0),discount=Math.min(sub,Math.max(0,Number(document.getElementById('discount')?.value||0))),rate=Math.max(0,Math.min(100,Number(document.getElementById('taxRate')?.value||0))),tax=(sub-discount)*rate/100,total=sub-discount+tax;
 document.getElementById('subtotal').textContent=fmt(sub);document.getElementById('taxAmount').textContent=fmt(tax);document.getElementById('grandTotal').textContent=fmt(total);
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function toast(message){let t=document.getElementById('toast');if(!t){t=document.createElement('div');t.id='toast';t.className='toast';document.body.appendChild(t);}t.textContent=message;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2600);}
async function checkout(){
 if(!cart.length){toast('Add a product before checkout.');return;}
 const btn=document.getElementById('checkoutBtn');btn.disabled=true;btn.textContent='Processing…';
 const subtotal=cart.reduce((a,x)=>a+x.qty*x.price,0),discount=Math.max(0,Number(document.getElementById('discount').value||0)),tax_rate=Math.max(0,Number(document.getElementById('taxRate').value||0)),total=subtotal-Math.min(discount,subtotal)+(subtotal-Math.min(discount,subtotal))*tax_rate/100;
 try{const res=await fetch('/api/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:cart.map(({id,qty})=>({id,qty})),discount,tax_rate,paid:total,payment_method:document.getElementById('paymentMethod').value})});const data=await res.json();if(!res.ok)throw new Error(data.error||'Payment failed.');window.location.href='/receipt/'+data.sale_id;}
 catch(e){toast(e.message);btn.disabled=false;btn.innerHTML='Complete payment <span>→</span>';}
}
const search=document.getElementById('productSearch');
// Product cards use data attributes instead of inline JavaScript. This avoids
// broken click handlers when product names contain quotes or apostrophes.
function productCard(p){
 const b=document.createElement('button'); b.type='button'; b.className='pos-product';
 b.dataset.productId=p.id; b.dataset.productName=p.name; b.dataset.productSku=p.sku;
 b.dataset.productPrice=p.price; b.dataset.productStock=p.stock;
 b.innerHTML=`<span class="product-art">${escapeHtml((p.category||'G').slice(0,1))}</span><span class="pos-product-name">${escapeHtml(p.name)}</span><small>${escapeHtml(p.sku)} · ${Number(p.stock)} in stock</small><b>${fmt(p.price)}</b>`;
 return b;
}
const productGrid=document.getElementById('productGrid');
if(productGrid){
 productGrid.addEventListener('click',e=>{
  const card=e.target.closest('.pos-product'); if(!card)return;
  addItem(Number(card.dataset.productId),card.dataset.productName,card.dataset.productSku,Number(card.dataset.productPrice),Number(card.dataset.productStock));
 });
}
if(search)search.addEventListener('input',async()=>{
 const q=search.value.trim();try{
  const r=await fetch('/api/products?q='+encodeURIComponent(q)); if(!r.ok)throw new Error('Could not load products');
  const items=await r.json(); const grid=document.getElementById('productGrid'); grid.replaceChildren();
  if(items.length)items.forEach(p=>grid.appendChild(productCard(p)));
  else grid.innerHTML='<div class="empty-state">No matching products.</div>';
 }catch(e){toast('Unable to load products. Please try again.');}
});


// Barcode scanning: supports USB/Bluetooth keyboard-wedge scanners and camera scanning
// on browsers that implement the native BarcodeDetector API (e.g. current Chrome).
const barcodeInput=document.getElementById('barcodeInput');
const addBarcodeBtn=document.getElementById('addBarcodeBtn');
const startCameraBtn=document.getElementById('startCameraBtn');
const stopCameraBtn=document.getElementById('stopCameraBtn');
const scannerCameraWrap=document.getElementById('scannerCameraWrap');
const scannerVideo=document.getElementById('scannerVideo');
const scannerStatus=document.getElementById('scannerStatus');
let scannerStream=null, scannerActive=false, lastScannedCode='', lastScannedAt=0;
async function addScannedBarcode(rawCode){
 const code=String(rawCode||'').trim();
 if(!code){toast('Scan a barcode or enter a product SKU.');return;}
 try{
  const response=await fetch('/api/products?q='+encodeURIComponent(code));
  if(!response.ok)throw new Error('Could not search products.');
  const products=await response.json();
  // SKU is the barcode value in this version; require an exact SKU match to avoid adding a similarly named item.
  const product=products.find(p=>String(p.sku||'').trim().toLowerCase()===code.toLowerCase());
  if(!product){toast('No product found for barcode/SKU: '+code);return;}
  if(Number(product.stock)<=0){toast('This product is out of stock.');return;}
  addItem(product.id,product.name,product.sku,product.price,product.stock);
  toast('Added '+product.name+' to the bill.');
  if(barcodeInput){barcodeInput.value='';barcodeInput.focus();}
 }catch(e){toast(e.message||'Barcode lookup failed.');}
}
if(addBarcodeBtn)addBarcodeBtn.addEventListener('click',()=>addScannedBarcode(barcodeInput?.value));
if(barcodeInput){
 barcodeInput.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();addScannedBarcode(barcodeInput.value);}});
 // Many USB barcode scanners type the code and send Enter automatically.
}
async function stopBarcodeCamera(){
 scannerActive=false;
 if(scannerStream){scannerStream.getTracks().forEach(track=>track.stop());scannerStream=null;}
 if(scannerVideo){scannerVideo.pause();scannerVideo.srcObject=null;}
 if(scannerCameraWrap)scannerCameraWrap.hidden=true;
 if(startCameraBtn)startCameraBtn.disabled=false;
}
async function startBarcodeCamera(){
 if(!('BarcodeDetector' in window)){toast('Camera barcode scanning is not supported by this browser. Use a USB scanner or enter the SKU.');return;}
 if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){toast('Camera access requires HTTPS or localhost.');return;}
 try{
  const detector=new BarcodeDetector({formats:['ean_13','ean_8','upc_a','upc_e','code_128','code_39','qr_code','itf','codabar']});
  scannerStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
  scannerVideo.srcObject=scannerStream;scannerCameraWrap.hidden=false;startCameraBtn.disabled=true;
  await scannerVideo.play();scannerActive=true;scannerStatus.textContent='Point the camera at the product barcode';
  const scanFrame=async()=>{
   if(!scannerActive)return;
   try{
    if(scannerVideo.readyState>=2){
     const codes=await detector.detect(scannerVideo);
     if(codes.length){const value=(codes[0].rawValue||'').trim(),now=Date.now();
      if(value&&(value!==lastScannedCode||now-lastScannedAt>1800)){
       lastScannedCode=value;lastScannedAt=now;scannerStatus.textContent='Scanned '+value+' — looking up product…';
       await addScannedBarcode(value);
       if(scannerActive)scannerStatus.textContent='Ready for next barcode';
      }
     }
    }
   }catch(err){scannerStatus.textContent='Could not read barcode. Adjust the camera and try again.';}
   if(scannerActive)requestAnimationFrame(scanFrame);
  };
  requestAnimationFrame(scanFrame);
 }catch(e){await stopBarcodeCamera();toast('Unable to open camera. Allow camera permission and try again.');}
}
if(startCameraBtn)startCameraBtn.addEventListener('click',startBarcodeCamera);
if(stopCameraBtn)stopCameraBtn.addEventListener('click',stopBarcodeCamera);
window.addEventListener('beforeunload',()=>{if(scannerStream)scannerStream.getTracks().forEach(track=>track.stop());});

// Keep the scanner field ready for a USB barcode scanner on the billing page.
if(barcodeInput){ setTimeout(()=>barcodeInput.focus(),150); }
