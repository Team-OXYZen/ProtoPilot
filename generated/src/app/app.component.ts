
import { Component } from '@angular/core';
import { RoomListComponent } from './room/room-list/room-list.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RoomListComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent {
  title = 'Hotel Room Management System';
}
