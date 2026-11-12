import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Icono } from '../icono/icono';

/** Espacio provisional para fotos del vehículo (IS-4 4.4): no hay carga de archivos en esta fase. */
@Component({
  selector: 'app-espacio-fotos',
  imports: [Icono],
  templateUrl: './espacio-fotos.html',
  styleUrl: './espacio-fotos.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EspacioFotos {}
