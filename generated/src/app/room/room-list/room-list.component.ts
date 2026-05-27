
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Observable } from 'rxjs';
import { Room } from '../room.model';
import { RoomService } from '../room.service';

@Component({
  selector: 'app-room-list',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './room-list.component.html',
  styleUrls: ['./room-list.component.scss']
})
export class RoomListComponent implements OnInit {
  rooms$!: Observable<Room[]>;

  constructor(private roomService: RoomService) { }

  ngOnInit(): void {
    this.rooms$ = this.roomService.getRooms();
  }
}
