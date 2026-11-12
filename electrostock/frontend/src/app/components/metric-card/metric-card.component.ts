import { Component, input } from '@angular/core';

@Component({
  selector: 'app-metric-card',
  styleUrl: './metric-card.component.css',
  templateUrl: './metric-card.component.html',
})
export class MetricCardComponent {
  readonly label = input.required<string>();
  readonly value = input.required<string | number>();
  readonly detail = input.required<string>();
}
