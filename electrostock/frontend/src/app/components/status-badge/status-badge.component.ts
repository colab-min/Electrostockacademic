import { Component, input } from '@angular/core';

@Component({
  selector: 'app-status-badge',
  styleUrl: './status-badge.component.css',
  templateUrl: './status-badge.component.html',
})
export class StatusBadgeComponent {
  readonly label = input.required<string>();
}
