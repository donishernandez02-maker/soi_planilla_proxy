<?php
$API_URL = getenv('SOI_PROXY_URL') ?: 'https://soiplanillaproxy-production.up.railway.app/planillas/consultar';
function soi_consultar($correo, $planilla){
  global $API_URL;
  $payload = json_encode(['correo'=>$correo,'numero_planilla'=>preg_replace('/\D+/','',$planilla)], JSON_UNESCAPED_UNICODE);
  $ch=curl_init($API_URL);
  curl_setopt_array($ch,[CURLOPT_RETURNTRANSFER=>true,CURLOPT_POST=>true,CURLOPT_HTTPHEADER=>['Content-Type: application/json'],CURLOPT_POSTFIELDS=>$payload,CURLOPT_TIMEOUT=>45]);
  $body=curl_exec($ch); $err=curl_error($ch); $status=curl_getinfo($ch,CURLINFO_HTTP_CODE); curl_close($ch);
  if($err) return ['ok'=>false,'error'=>"Error de red: $err"]; $json=json_decode($body,true); if(!is_array($json)) return ['ok'=>false,'error'=>'Respuesta inválida'];
  if($status>=400) return ['ok'=>false,'error'=>$json['error']??("HTTP $status")]; return $json;
}
$consulta=null; $errores=[];
if($_SERVER['REQUEST_METHOD']==='POST'){
  $correo=filter_var($_POST['correo']??'', FILTER_VALIDATE_EMAIL);
  $planilla=trim($_POST['planilla']??'');
  if(!$correo) $errores[]='Ingresa un correo válido.';
  if($planilla==='') $errores[]='Ingresa el número de planilla.';
  if(!$errores){ $consulta=soi_consultar($correo,$planilla); if(!($consulta['ok']??false)) $errores[]=$consulta['error']??'No se pudo consultar.'; }
}
?><!doctype html><html lang="es"><head><meta charset="utf-8"><title>SOI - Pago Planilla</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{background:#f7f8fa}.card{border-radius:14px}.row-item{padding:10px 0;border-bottom:1px solid #eee}.row-item:last-child{border-bottom:0}.lbl{color:#6b7280}.val{font-weight:600}.money{color:#13795b}</style>
</head><body><div class="container py-4"><div class="row justify-content-center"><div class="col-lg-9">
<div class="card shadow-sm mb-4"><div class="card-body"><form method="post" class="row g-3">
<div class="col-md-6"><label class="form-label">Correo</label><input type="email" name="correo" class="form-control" required value="<?= htmlspecialchars($_POST['correo']??'') ?>"></div>
<div class="col-md-6"><label class="form-label">Número de Planilla</label><input type="text" name="planilla" class="form-control" required value="<?= htmlspecialchars($_POST['planilla']??'') ?>"></div>
<div class="col-12 text-end"><button class="btn btn-primary">Buscar</button></div></form></div></div>
<?php if($errores): ?><div class="alert alert-danger"><?php foreach($errores as $e): ?><div>• <?= htmlspecialchars($e) ?></div><?php endforeach; ?></div><?php endif; ?>
<?php if($consulta && ($consulta['ok']??false)): $d=$consulta['data']??[]; ?>
<div class="card shadow-sm"><div class="card-body"><h2 class="h5 mb-3">Resultado de la Búsqueda</h2>
<div class="row row-item"><div class="col-md-6 lbl">Razón Social / Nombres y Apellidos:</div><div class="col-md-6 text-md-end val"><?= htmlspecialchars($d['razon_social']??'-') ?></div></div>
<div class="row row-item"><div class="col-md-6 lbl">Periodo Liquidación Salud:</div><div class="col-md-6 text-md-end val"><?= htmlspecialchars($d['periodo_salud']??'-') ?></div></div>
<div class="row row-item"><div class="col-md-6 lbl">Tipo de Planilla:</div><div class="col-md-6 text-md-end val"><?= htmlspecialchars($d['tipo_planilla']??'-') ?></div></div>
<div class="row row-item"><div class="col-md-6 lbl">Días de Mora:</div><div class="col-md-6 text-md-end val"><?= htmlspecialchars($d['dias_mora']??'0') ?></div></div>
<div class="row row-item"><div class="col-md-6 lbl">Valor Mora:</div><div class="col-md-6 text-md-end val"><?= htmlspecialchars($d['valor_mora']??'$ 0') ?></div></div>
<div class="row row-item"><div class="col-md-6 lbl">Día de Pago Efectivo:</div><div class="col-md-6 text-md-end val"><?= htmlspecialchars($d['dia_pago_efectivo']??'-') ?></div></div>
<div class="row row-item"><div class="col-md-6 lbl">Valor a Pagar:</div><div class="col-md-6 text-md-end val money"><?= htmlspecialchars($d['valor_a_pagar']??'-') ?></div></div>
</div></div><?php endif; ?>
</div></div></div></body></html>
